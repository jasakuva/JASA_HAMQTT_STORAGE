import json

from flask import Flask, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func, or_, select
from .config import settings
from .db import (
    Base,
    HAConnection,
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
        return render_template("mqtt.html", topics=topics, messages=recent, search=search)

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

    @app.route("/settings", methods=["GET", "POST"])
    def settings_view():
        with SessionLocal() as session:
            if request.method == "POST":
                kind = request.form.get("kind")
                if kind == "ha":
                    session.add(HAConnection(
                        name=request.form["name"], base_url=request.form["base_url"].rstrip("/"),
                        access_token=request.form.get("access_token") or None,
                        enabled=bool(request.form.get("enabled")),
                    ))
                elif kind == "mqtt":
                    connection = MQTTConnection(
                        name=request.form["name"], host=request.form["host"],
                        port=int(request.form.get("port", "1883")), username=request.form.get("username") or None,
                        password=request.form.get("password") or None, enabled=bool(request.form.get("enabled")),
                    )
                    session.add(connection)
                    session.flush()
                    session.add(IngestionSubscription(mqtt_connection_id=connection.id, topic_filter=request.form.get("topic_filter") or "#", qos=0, enabled=True))
                session.commit()
                return redirect(url_for("settings_view"))
            ha_connections = session.scalars(select(HAConnection).order_by(HAConnection.name)).all()
            mqtt_connections = session.scalars(select(MQTTConnection).order_by(MQTTConnection.name)).all()
        return render_template("settings.html", ha_connections=ha_connections, mqtt_connections=mqtt_connections)

    @app.get("/ha")
    def ha_view():
        search = request.args.get("q", "").strip()
        with SessionLocal() as session:
            entity_query = (
                select(HAEntity)
                .join(Object, Object.id == HAEntity.object_id)
                .order_by(HAEntity.entity_id)
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
        return render_template("ha.html", entities=entities, current=current, search=search)

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
