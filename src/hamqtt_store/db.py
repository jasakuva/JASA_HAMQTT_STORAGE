from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, create_engine, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.types import UserDefinedType
from .config import settings

def utcnow():
    return datetime.now(timezone.utc)

class Vector(UserDefinedType):
    cache_ok = True
    def __init__(self, dimensions=1536): self.dimensions = dimensions
    def get_col_spec(self, **kw): return f"vector({self.dimensions})"

class Base(DeclarativeBase): pass

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

class SystemSetting(Base, TimestampMixin):
    __tablename__ = "system_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    setting_key: Mapped[str] = mapped_column(String(150), unique=True)
    setting_value: Mapped[dict] = mapped_column(JSON, default=dict)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)

class HAConnection(Base, TimestampMixin):
    __tablename__ = "ha_connections"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    base_url: Mapped[str] = mapped_column(String(500))
    access_token: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    verify_tls: Mapped[bool] = mapped_column(Boolean, default=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

class MQTTConnection(Base, TimestampMixin):
    __tablename__ = "mqtt_connections"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer, default=1883)
    username: Mapped[str | None] = mapped_column(String(255))
    password: Mapped[str | None] = mapped_column(Text)
    tls_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    client_id: Mapped[str | None] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    subscriptions: Mapped[list["IngestionSubscription"]] = relationship(cascade="all, delete-orphan")

class IngestionSubscription(Base):
    __tablename__ = "ingestion_subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    mqtt_connection_id: Mapped[int] = mapped_column(ForeignKey("mqtt_connections.id", ondelete="CASCADE"))
    topic_filter: Mapped[str] = mapped_column(String(500))
    qos: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class Object(Base, TimestampMixin):
    __tablename__ = "objects"
    __table_args__ = (UniqueConstraint("source_type", "source_identifier"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    object_type: Mapped[str] = mapped_column(String(50))
    source_type: Mapped[str] = mapped_column(String(50))
    source_identifier: Mapped[str] = mapped_column(String(1000))
    display_name: Mapped[str | None] = mapped_column(String(500))
    nickname: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class HAEntity(Base):
    __tablename__ = "ha_entities"
    id: Mapped[int] = mapped_column(primary_key=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), unique=True)
    ha_connection_id: Mapped[int] = mapped_column(ForeignKey("ha_connections.id", ondelete="CASCADE"))
    entity_id: Mapped[str] = mapped_column(String(255), index=True)
    domain: Mapped[str] = mapped_column(String(100))
    platform: Mapped[str | None] = mapped_column(String(255))
    device_id: Mapped[str | None] = mapped_column(String(255))
    area_id: Mapped[str | None] = mapped_column(String(255))
    unique_id: Mapped[str | None] = mapped_column(String(500))
    original_name: Mapped[str | None] = mapped_column(String(500))
    raw_entity: Mapped[dict] = mapped_column(JSON, default=dict)

class HAStateCurrent(Base):
    __tablename__ = "ha_state_current"
    id: Mapped[int] = mapped_column(primary_key=True)
    ha_entity_id: Mapped[int] = mapped_column(ForeignKey("ha_entities.id", ondelete="CASCADE"), unique=True)
    state_text: Mapped[str | None] = mapped_column(Text)
    state_numeric: Mapped[float | None] = mapped_column(Float)
    state_boolean: Mapped[bool | None] = mapped_column(Boolean)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    last_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_state: Mapped[dict] = mapped_column(JSON, default=dict)

class HAStateHistory(Base):
    __tablename__ = "ha_state_history"
    __table_args__ = (UniqueConstraint("ha_entity_id", "observed_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    ha_entity_id: Mapped[int] = mapped_column(ForeignKey("ha_entities.id", ondelete="CASCADE"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    state_text: Mapped[str | None] = mapped_column(Text)
    state_numeric: Mapped[float | None] = mapped_column(Float)
    state_boolean: Mapped[bool | None] = mapped_column(Boolean)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_state: Mapped[dict] = mapped_column(JSON, default=dict)

class MQTTTopic(Base):
    __tablename__ = "mqtt_topics"
    __table_args__ = (UniqueConstraint("mqtt_connection_id", "topic"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), unique=True)
    mqtt_connection_id: Mapped[int] = mapped_column(ForeignKey("mqtt_connections.id", ondelete="CASCADE"))
    topic: Mapped[str] = mapped_column(String(1000), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    message_count: Mapped[int] = mapped_column(Integer, default=0)

class MQTTMessage(Base):
    __tablename__ = "mqtt_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    mqtt_connection_id: Mapped[int] = mapped_column(ForeignKey("mqtt_connections.id", ondelete="CASCADE"))
    mqtt_topic_id: Mapped[int] = mapped_column(ForeignKey("mqtt_topics.id", ondelete="CASCADE"), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    qos: Mapped[int] = mapped_column(Integer, default=0)
    retain: Mapped[bool] = mapped_column(Boolean, default=False)
    duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    payload_type: Mapped[str] = mapped_column(String(30))
    payload_text: Mapped[str | None] = mapped_column(Text)
    payload_json: Mapped[dict | list | None] = mapped_column(JSON)
    payload_binary: Mapped[bytes | None] = mapped_column(LargeBinary)
    payload_size: Mapped[int] = mapped_column(Integer, default=0)
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)

class MQTTPayloadField(Base):
    __tablename__ = "mqtt_payload_fields"
    __table_args__ = (UniqueConstraint("mqtt_topic_id", "field_path"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    mqtt_topic_id: Mapped[int] = mapped_column(ForeignKey("mqtt_topics.id", ondelete="CASCADE"))
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), unique=True)
    field_path: Mapped[str] = mapped_column(String(1000))
    field_name: Mapped[str] = mapped_column(String(500))
    data_type: Mapped[str] = mapped_column(String(30))
    unit: Mapped[str | None] = mapped_column(String(50))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    observation_count: Mapped[int] = mapped_column(Integer, default=0)

class MQTTObservation(Base):
    __tablename__ = "mqtt_observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    mqtt_topic_id: Mapped[int] = mapped_column(ForeignKey("mqtt_topics.id", ondelete="CASCADE"), index=True)
    mqtt_payload_field_id: Mapped[int] = mapped_column(ForeignKey("mqtt_payload_fields.id", ondelete="CASCADE"), index=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"))
    source_message_id: Mapped[int] = mapped_column(ForeignKey("mqtt_messages.id", ondelete="CASCADE"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    value_type: Mapped[str] = mapped_column(String(30))
    value_text: Mapped[str | None] = mapped_column(Text)
    value_numeric: Mapped[float | None] = mapped_column(Float)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean)
    value_json: Mapped[dict | list | None] = mapped_column(JSON)
    unit: Mapped[str | None] = mapped_column(String(50))
    quality: Mapped[str] = mapped_column(String(30), default="good")
    raw_field_value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)

class MQTTCurrentValue(Base):
    __tablename__ = "mqtt_current_values"
    id: Mapped[int] = mapped_column(primary_key=True)
    mqtt_payload_field_id: Mapped[int] = mapped_column(ForeignKey("mqtt_payload_fields.id", ondelete="CASCADE"), unique=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"))
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    value_type: Mapped[str] = mapped_column(String(30))
    value_text: Mapped[str | None] = mapped_column(Text)
    value_numeric: Mapped[float | None] = mapped_column(Float)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean)
    value_json: Mapped[dict | list | None] = mapped_column(JSON)
    unit: Mapped[str | None] = mapped_column(String(50))

class MQTTParseEvent(Base):
    __tablename__ = "mqtt_parse_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    mqtt_message_id: Mapped[int] = mapped_column(ForeignKey("mqtt_messages.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(40))
    error_message: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ObjectLink(Base, TimestampMixin):
    __tablename__ = "object_links"
    __table_args__ = (UniqueConstraint("from_object_id", "to_object_id", "link_type"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    from_object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"))
    to_object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"))
    link_type: Mapped[str] = mapped_column(String(50))
    direction: Mapped[str] = mapped_column(String(30), default="one_way")
    confidence: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(30), default="manual")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)

class Embedding(Base):
    __tablename__ = "embeddings"
    id: Mapped[int] = mapped_column(primary_key=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), unique=True)
    source_text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list | None] = mapped_column(Vector(1536))
    embedding_model: Mapped[str | None] = mapped_column(String(150))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
