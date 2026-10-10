import json

from flask import Flask, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func, or_, select
from .config import settings
from .db import (
    Base,
    HAConnection,
    ApplicationLog,
    HAEntity,
    HAStateCurrent,
    HAStateHistory,
    IngestionSubscription,
    MQTTConnection,
    MQTTCurrentValue,
    MQTTMessage,
    MQTTObservation,
    MQTTPayloadField,
    MQTTTopic,
    Object,
    ObjectLink,
    SystemSetting,
    SessionLocal,
    engine,
)

def create_app():
    app = Flask(__name__, template_folder="../../templates", static_folder="../../static")
    app.config["SECRET_KEY"] = settings.secret_key
    app.jinja_env.filters["pretty_json"] = lambda value: json.dumps(value or {}, indent=2, sort_keys=True, default=str)

    @app.get("/")
    def dashboard():
        with SessionLocal() as session:
            counts = {
                "objects": session.scalar(select(func.count(Object.id))) or 0,
                "ha_entities": session.scalar(select(func.count(HAEntity.id))) or 0,
                "mqtt_topics": session.scalar(select(func.count(MQTTTopic.id))) or 0,
                "mqtt_messages": session.scalar(select(func.count(MQTTMessage.id))) or 0,
                "links": session.scalar(select(func.count(ObjectLink.id))) or 0,
            }
        return render_template("dashboard.html", counts=counts)

    @app.get("/health")
    def health():
        try:
            with engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
            return jsonify(status="ok", database="ok")
        except Exception as exc:
            return jsonify(status="error", database="error", error=str(exc)), 503

    @app.get("/objects")
    def objects():
        search = request.args.get("q", "").strip()
        with SessionLocal() as session:
            query = select(Object).order_by(Object.source_type, Object.source_identifier)
            if search:
                pattern = f"%{search}%"
                query = query.where(or_(
                    Object.source_identifier.ilike(pattern),
                    Object.display_name.ilike(pattern),
                    Object.nickname.ilike(pattern),
                    Object.description.ilike(pattern),
                ))
            rows = session.scalars(query.limit(500)).all()
        return render_template("objects.html", objects=rows, search=search)

    @app.post("/objects/<int:object_id>")
    def update_object(object_id):
        with SessionLocal() as session:
            obj = session.get(Object, object_id)
            if not obj: return "Not found", 404
            obj.nickname = request.form.get("nickname") or None
            obj.description = request.form.get("description") or None
            session.commit()
        return redirect(url_for("objects"))

    @app.get("/mqtt")
    def mqtt_view():
        search = request.args.get("q", "").strip()
        with SessionLocal() as session:
            topic_query = select(MQTTTopic).order_by(MQTTTopic.topic)
            if search:
                topic_query = topic_query.where(MQTTTopic.topic.ilike(f"%{search}%"))
            topics = session.scalars(topic_query.limit(500)).all()
            recent = session.scalars(select(MQTTMessage).order_by(MQTTMessage.received_at.desc()).limit(100)).all()
            topic_names = {
                topic.id: topic.topic
                for topic in session.scalars(
                    select(MQTTTopic).where(
                        MQTTTopic.id.in_({message.mqtt_topic_id for message in recent})
                    )
                ).all()
            } if recent else {}
        return render_template("mqtt.html", topics=topics, messages=recent, topic_names=topic_names, search=search)

    @app.get("/mqtt/topics/<int:topic_id>")
    def mqtt_topic_detail(topic_id):
        with SessionLocal() as session:
            topic = session.get(MQTTTopic, topic_id)
            if not topic:
                return "MQTT topic not found", 404
            messages = session.scalars(
                select(MQTTMessage)
                .where(MQTTMessage.mqtt_topic_id == topic_id)
                .order_by(MQTTMessage.received_at.desc())
                .limit(200)
            ).all()
            fields = session.scalars(
                select(MQTTPayloadField)
                .where(MQTTPayloadField.mqtt_topic_id == topic_id)
                .order_by(MQTTPayloadField.field_path)
            ).all()
            current_values = {
                row.mqtt_payload_field_id: row
                for row in session.scalars(
                    select(MQTTCurrentValue).where(
                        MQTTCurrentValue.mqtt_payload_field_id.in_([field.id for field in fields])
                    )
                ).all()
            } if fields else {}
            observations = session.scalars(
                select(MQTTObservation)
                .where(MQTTObservation.mqtt_topic_id == topic_id)
                .order_by(MQTTObservation.observed_at.desc())
                .limit(500)
            ).all()
        return render_template(
            "mqtt_topic.html",
            topic=topic,
            messages=messages,
            fields=fields,
            current_values=current_values,
            observations=observations,
        )

    @app.get("/mqtt/fields/<int:field_id>")
    def mqtt_field_history(field_id):
        with SessionLocal() as session:
            field = session.get(MQTTPayloadField, field_id)
            if not field:
                return "MQTT field not found", 404
            topic = session.get(MQTTTopic, field.mqtt_topic_id)
            history = session.scalars(
                select(MQTTObservation)
                .where(MQTTObservation.mqtt_payload_field_id == field_id)
                .order_by(MQTTObservation.observed_at.desc())
                .limit(500)
            ).all()
            source_messages = {
                message.id: message
                for message in session.scalars(
                    select(MQTTMessage).where(
                        MQTTMessage.id.in_([row.source_message_id for row in history])
                    )
                ).all()
            } if history else {}
        return render_template(
            "mqtt_field.html",
            topic=topic,
            field=field,
            history=history,
            source_messages=source_messages,
        )

    @app.route("/settings", methods=["GET", "POST"])
    def settings_view():
        with SessionLocal() as session:
            if request.method == "POST":
                kind = request.form.get("kind")
                if kind == "mcp":
                    enabled = bool(request.form.get("mcp_enabled"))
                    access_level = request.form.get("mcp_access_level", "read_only")
                    if access_level not in {"read_only"}:
                        access_level = "read_only"
                    setting = session.scalar(select(SystemSetting).where(SystemSetting.setting_key == "mcp"))
                    if not setting:
                        setting = SystemSetting(setting_key="mcp", setting_value={}, is_secret=False)
                        session.add(setting)
                    setting.setting_value = {"enabled": enabled, "access_level": access_level}
                elif kind == "ha":
                    ha_connections = session.scalars(select(HAConnection).order_by(HAConnection.id)).all()
                    connection = ha_connections[0] if ha_connections else HAConnection()
                    if not ha_connections:
                        session.add(connection)
                    connection.name = request.form["name"].strip()
                    connection.base_url = request.form["base_url"].rstrip("/")
                    submitted_token = request.form.get("access_token", "").strip()
                    if submitted_token:
                        connection.access_token = submitted_token
                    connection.enabled = bool(request.form.get("enabled"))
                    for duplicate in ha_connections[1:]:
                        duplicate.enabled = False
                elif kind == "mqtt":
                    # Prefer the enabled row so Settings edits the same
                    # connection that the MQTT worker actually loads.
                    mqtt_connections = session.scalars(
                        select(MQTTConnection).order_by(MQTTConnection.enabled.desc(), MQTTConnection.id)
                    ).all()
                    connection = mqtt_connections[0] if mqtt_connections else MQTTConnection()
                    if not mqtt_connections:
                        session.add(connection)
                    connection.name = request.form["name"].strip()
                    connection.host = request.form["host"].strip()
                    try:
                        connection.port = int(request.form.get("port", "1883"))
                    except ValueError:
                        return "MQTT port must be a number", 400
                    if not 1 <= connection.port <= 65535:
                        return "MQTT port must be between 1 and 65535", 400
                    connection.client_id = request.form.get("client_id", "").strip() or None
                    connection.username = request.form.get("username", "").strip() or None
                    submitted_password = request.form.get("password", "").strip()
                    # Blank password fields mean "keep the saved password";
                    # credentials are never echoed back into the form.
                    if submitted_password:
                        connection.password = submitted_password
                    connection.enabled = bool(request.form.get("enabled"))
                    for duplicate in mqtt_connections[1:]:
                        duplicate.enabled = False
                    session.flush()
                    subscriptions = session.scalars(
                        select(IngestionSubscription)
                        .where(IngestionSubscription.mqtt_connection_id == connection.id)
                        .order_by(IngestionSubscription.id)
                    ).all()
                    subscription = subscriptions[0] if subscriptions else IngestionSubscription(mqtt_connection_id=connection.id)
                    if not subscriptions:
                        session.add(subscription)
                    subscription.topic_filter = request.form.get("topic_filter", "").strip() or "#"
                    subscription.qos = 0
                    subscription.enabled = True
                    for duplicate in subscriptions[1:]:
                        duplicate.enabled = False
                session.commit()
                return redirect(url_for("settings_view"))
            ha_connection = session.scalar(select(HAConnection).order_by(HAConnection.id))
            mqtt_connection = session.scalar(
                select(MQTTConnection).order_by(MQTTConnection.enabled.desc(), MQTTConnection.id)
            )
            mqtt_subscription = None
            if mqtt_connection:
                mqtt_subscription = session.scalar(
                    select(IngestionSubscription)
                    .where(IngestionSubscription.mqtt_connection_id == mqtt_connection.id)
                    .order_by(IngestionSubscription.id)
                )
            mcp_setting = session.scalar(select(SystemSetting).where(SystemSetting.setting_key == "mcp"))
            mcp_config = mcp_setting.setting_value if mcp_setting else {"enabled": False, "access_level": "read_only"}
        return render_template(
            "settings.html",
            ha_connection=ha_connection,
            mqtt_connection=mqtt_connection,
            mqtt_subscription=mqtt_subscription,
            mcp_config=mcp_config,
        )

    @app.get("/logs")
    def logs_view():
        level = request.args.get("level", "").upper().strip()
        source = request.args.get("source", "").strip()
        search = request.args.get("q", "").strip()
        with SessionLocal() as session:
            query = select(ApplicationLog).order_by(ApplicationLog.created_at.desc()).limit(500)
            if level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
                query = query.where(ApplicationLog.level == level)
            else:
                level = ""
            if source:
                query = query.where(ApplicationLog.source.ilike(f"%{source}%"))
            if search:
                query = query.where(or_(ApplicationLog.message.ilike(f"%{search}%"), ApplicationLog.event.ilike(f"%{search}%")))
            logs = session.scalars(query).all()
        return render_template("logs.html", logs=logs, level=level, source=source, search=search)

    @app.get("/ha")
    def ha_view():
        search = request.args.get("q", "").strip()
        sort = request.args.get("sort", "entity_id")
        direction = request.args.get("direction", "asc")
        sort_fields = {"entity_id", "domain", "name", "state", "last_changed"}
        if sort not in sort_fields:
            sort = "entity_id"
        if direction not in {"asc", "desc"}:
            direction = "asc"
        with SessionLocal() as session:
            entity_query = (
                select(HAEntity)
                .join(Object, Object.id == HAEntity.object_id)
            )
            if search:
                pattern = f"%{search}%"
                entity_query = entity_query.where(or_(
                    HAEntity.entity_id.ilike(pattern),
                    HAEntity.original_name.ilike(pattern),
                    Object.display_name.ilike(pattern),
                    Object.nickname.ilike(pattern),
                ))
            entities = session.scalars(entity_query.limit(500)).all()
            current = {row.ha_entity_id: row for row in session.scalars(select(HAStateCurrent)).all()}

        def sort_value(entity):
            state = current.get(entity.id)
            values = {
                "entity_id": entity.entity_id,
                "domain": entity.domain,
                "name": entity.original_name or "",
                "state": state.state_text if state else None,
                "last_changed": state.last_changed_at if state else None,
            }
            value = values[sort]
            return value.lower() if isinstance(value, str) else value

        present = [entity for entity in entities if sort_value(entity) is not None]
        missing = [entity for entity in entities if sort_value(entity) is None]
        present.sort(key=sort_value, reverse=direction == "desc")
        entities = present + missing
        return render_template(
            "ha.html",
            entities=entities,
            current=current,
            search=search,
            sort=sort,
            direction=direction,
        )

    @app.get("/ha/entities/<int:entity_id>")
    def ha_entity_detail(entity_id):
        with SessionLocal() as session:
            entity = session.get(HAEntity, entity_id)
            if not entity:
                return "Home Assistant entity not found", 404
            current = session.scalar(
                select(HAStateCurrent).where(HAStateCurrent.ha_entity_id == entity_id)
            )
            history = session.scalars(
                select(HAStateHistory)
                .where(HAStateHistory.ha_entity_id == entity_id)
                .order_by(HAStateHistory.observed_at.desc())
                .limit(500)
            ).all()
            obj = session.get(Object, entity.object_id)
        return render_template(
            "ha_entity.html",
            entity=entity,
            object=obj,
            current=current,
            history=history,
        )

    @app.get("/api/objects")
    def api_objects():
        with SessionLocal() as session:
            rows = session.scalars(select(Object).order_by(Object.id)).all()
            return jsonify([{"id": o.id, "type": o.object_type, "source": o.source_type, "identifier": o.source_identifier,
                            "name": o.nickname or o.display_name} for o in rows])

    @app.get("/api/mqtt/topics/<int:topic_id>/observations")
    def api_observations(topic_id):
        with SessionLocal() as session:
            rows = session.scalars(select(MQTTObservation).where(MQTTObservation.mqtt_topic_id == topic_id)
                                   .order_by(MQTTObservation.observed_at.desc()).limit(500)).all()
            return jsonify([{"field_id": r.mqtt_payload_field_id, "type": r.value_type, "text": r.value_text,
                             "number": r.value_numeric, "boolean": r.value_boolean, "observed_at": r.observed_at.isoformat()} for r in rows])

    return app
