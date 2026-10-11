import csv
import io
import json
from datetime import UTC, datetime, timedelta

from flask import Flask, Response, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func, or_, select
from .config import settings
from .db import (
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

    def parse_range():
        now = datetime.now(UTC)
        default_from = now - timedelta(hours=24)
        values = []
        for name, default in (("from", default_from), ("to", now)):
            raw = request.args.get(name, "").strip()
            if not raw:
                values.append(default)
                continue
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                values.append((parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).astimezone(UTC))
            except ValueError:
                values.append(None)
        if any(value is None for value in values) or values[0] >= values[1]:
            return None, None
        return values

    def selected_ids():
        raw = request.args.getlist("object_id") or request.args.getlist("object_ids")
        ids = []
        for value in raw:
            for item in value.split(","):
                try:
                    object_id = int(item)
                except ValueError:
                    continue
                if object_id not in ids:
                    ids.append(object_id)
        return ids

    def series_catalog(session):
        rows = [dict(row) for row in session.execute(select(
            Object.id.label("id"), Object.nickname.label("nickname"), Object.display_name.label("display_name"),
            HAEntity.entity_id.label("identifier"),
        ).join(HAEntity, HAEntity.object_id == Object.id)).mappings().all()]
        rows = [{"id": row["id"], "label": row["nickname"] or row["display_name"] or row["identifier"],
                 "identifier": row["identifier"], "source": "Home Assistant", "unit": None} for row in rows]
        mqtt_rows = session.execute(select(
            Object.id.label("id"), Object.nickname.label("nickname"), Object.display_name.label("display_name"),
            MQTTPayloadField.field_path.label("identifier"), MQTTPayloadField.unit.label("unit"),
        ).join(MQTTPayloadField, MQTTPayloadField.object_id == Object.id)).mappings().all()
        rows.extend({"id": row["id"], "label": row["nickname"] or row["display_name"] or row["identifier"],
                     "identifier": row["identifier"], "source": "MQTT", "unit": row["unit"]} for row in mqtt_rows)
        rows = list({row["id"]: row for row in rows}.values())
        return sorted(rows, key=lambda row: (row["source"], row["label"]))

    def history_rows(session, object_ids, start, end, downsample=False):
        result = []
        entities = session.execute(select(
            HAEntity.id.label("entity_id"), HAEntity.entity_id.label("identifier"),
            Object.nickname.label("nickname"), Object.display_name.label("display_name"),
        ).join(Object, Object.id == HAEntity.object_id).where(HAEntity.object_id.in_(object_ids))).mappings().all() if object_ids else []
        fields = session.execute(select(
            MQTTPayloadField.id.label("field_id"), MQTTPayloadField.field_path.label("identifier"),
            MQTTPayloadField.unit.label("unit"), Object.nickname.label("nickname"),
            Object.display_name.label("display_name"),
        ).join(Object, Object.id == MQTTPayloadField.object_id).where(
            MQTTPayloadField.object_id.in_(object_ids))).mappings().all() if object_ids else []
        fields = list({field["field_id"]: field for field in fields}.values())
        for entity in entities:
            rows = session.execute(select(
                HAStateHistory.observed_at, HAStateHistory.state_text,
                HAStateHistory.state_numeric, HAStateHistory.state_boolean,
            ).where(
                HAStateHistory.ha_entity_id == entity["entity_id"], HAStateHistory.observed_at >= start,
                HAStateHistory.observed_at <= end).order_by(HAStateHistory.observed_at)).mappings().all()
            for row in rows:
                value = row["state_numeric"] if row["state_numeric"] is not None else row["state_boolean"] if row["state_boolean"] is not None else row["state_text"]
                result.append({"timestamp": row["observed_at"].isoformat(), "series": entity["nickname"] or entity["display_name"] or entity["identifier"],
                               "source": "Home Assistant", "identifier": entity["identifier"], "value": value,
                               "value_type": "numeric" if row["state_numeric"] is not None else "boolean" if row["state_boolean"] is not None else "text",
                               "unit": None, "state": row["state_text"]})
        for field in fields:
            rows = session.execute(select(
                MQTTObservation.observed_at, MQTTObservation.value_type,
                MQTTObservation.value_text, MQTTObservation.value_numeric,
                MQTTObservation.value_boolean, MQTTObservation.unit,
            ).where(
                MQTTObservation.mqtt_payload_field_id == field["field_id"], MQTTObservation.observed_at >= start,
                MQTTObservation.observed_at <= end).order_by(MQTTObservation.observed_at)).mappings().all()
            for row in rows:
                value = row["value_numeric"] if row["value_numeric"] is not None else row["value_boolean"] if row["value_boolean"] is not None else row["value_text"]
                result.append({"timestamp": row["observed_at"].isoformat(), "series": field["nickname"] or field["display_name"] or field["identifier"],
                               "source": "MQTT", "identifier": field["identifier"], "value": value,
                               "value_type": row["value_type"], "unit": row["unit"] or field["unit"], "state": row["value_text"]})
        result.sort(key=lambda row: row["timestamp"])
        return downsample_rows(result) if downsample else result

    def downsample_rows(rows, max_points=4000):
        numeric = [row for row in rows if isinstance(row["value"], (int, float)) and not isinstance(row["value"], bool)]
        if len(numeric) <= max_points:
            return rows
        by_series = {}
        for row in numeric:
            by_series.setdefault(row["series"], []).append(row)
        stride = max(1, (len(numeric) + max_points - 1) // max_points)
        keep = {id(row): row for series in by_series.values() for row in series[::stride]}
        return [row for row in rows if id(row) in keep]

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

    @app.get("/graph")
    def graph_view():
        start, end = parse_range()
        object_ids = selected_ids()
        with SessionLocal() as session:
            catalog = series_catalog(session)
            valid_ids = {item["id"] for item in catalog}
            error = ("Select a valid time range." if start is None else
                     "Select between 1 and 4 available series." if not 1 <= len(object_ids) <= 4 or not set(object_ids) <= valid_ids else None)
            data = history_rows(session, object_ids, start, end, downsample=True) if not error else []
        return render_template("graph.html", catalog=catalog, selected=object_ids, data=data, start=start, end=end, error=error,
                               standalone=request.args.get("standalone") == "1")

    @app.get("/export")
    def export_view():
        start, end = parse_range()
        object_ids = selected_ids()
        with SessionLocal() as session:
            catalog = series_catalog(session)
            valid_ids = {item["id"] for item in catalog}
            error = ("Select a valid time range." if start is None else
                     "Select between 1 and 10 available series." if not 1 <= len(object_ids) <= 10 or not set(object_ids) <= valid_ids else None)
            data = history_rows(session, object_ids, start, end) if not error else []
        if request.args.get("download") == "1" and not error:
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=["timestamp", "series", "source", "identifier", "value", "value_type", "unit", "state"])
            writer.writeheader()
            writer.writerows(data)
            return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=hamqtt-export.csv"})
        return render_template("export.html", catalog=catalog, selected=object_ids, start=start, end=end, error=error)

    @app.get("/plot/<int:object_id>")
    def plot_object(object_id):
        return redirect(url_for("graph_view", object_id=object_id, standalone=1))

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
                if kind == "retention":
                    try:
                        history_days = int(request.form.get("history_days", "365"))
                    except ValueError:
                        return "History retention must be a whole number of days", 400
                    if not 1 <= history_days <= 3650:
                        return "History retention must be between 1 and 3650 days", 400
                    setting = session.scalar(select(SystemSetting).where(SystemSetting.setting_key == "retention"))
                    if not setting:
                        setting = SystemSetting(setting_key="retention", setting_value={}, is_secret=False)
                        session.add(setting)
                    setting.setting_value = {"history_days": history_days}
                elif kind == "mcp":
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
            retention_setting = session.scalar(select(SystemSetting).where(SystemSetting.setting_key == "retention"))
            retention_config = retention_setting.setting_value if retention_setting else {"history_days": 365}
        return render_template(
            "settings.html",
            ha_connection=ha_connection,
            mqtt_connection=mqtt_connection,
            mqtt_subscription=mqtt_subscription,
            mcp_config=mcp_config,
            retention_config=retention_config,
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
