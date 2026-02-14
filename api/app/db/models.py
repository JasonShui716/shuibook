import uuid
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Text,
    Boolean,
    Float,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    type = Column(String(50), nullable=False)
    config = Column(JSONB, nullable=False)
    topics = Column(ARRAY(String), nullable=False)
    weight = Column(Float, nullable=False, default=1.0)
    fetch_interval_minutes = Column(Integer, nullable=False, default=240)
    last_fetch_at = Column(DateTime(timezone=True))
    active = Column(Boolean, nullable=False, default=True)

    items = relationship("Item", back_populates="source")


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True)
    url = Column(Text, nullable=False)
    url_canonical = Column(Text, nullable=False, unique=True)
    content_hash = Column(String(64), nullable=False, unique=True)

    title = Column(Text, nullable=True)
    title_zh = Column(Text, nullable=True)
    summary_zh = Column(Text, nullable=True)
    summary_json = Column(JSONB, nullable=True)
    excerpt = Column(Text, nullable=True)
    translation_excerpt = Column(Text, nullable=True)
    translation_full_zh = Column(Text, nullable=True)

    image_url = Column(Text, nullable=True)
    site_name = Column(String(255), nullable=True)
    world = Column(String(20), nullable=False, default="real")
    ai_topic = Column(String(255), nullable=True)
    ai_prompt = Column(Text, nullable=True)
    ai_model = Column(String(100), nullable=True)
    ai_generated_at = Column(DateTime(timezone=True))

    is_favorite = Column(Boolean, nullable=False, default=False)
    favorited_at = Column(DateTime(timezone=True))
    is_disliked = Column(Boolean, nullable=False, default=False)
    disliked_at = Column(DateTime(timezone=True))
    view_count = Column(Integer, nullable=False, default=0)
    last_viewed_at = Column(DateTime(timezone=True))
    total_read_seconds = Column(Integer, nullable=False, default=0)
    long_read_count = Column(Integer, nullable=False, default=0)

    published_at = Column(DateTime(timezone=True))
    fetched_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    source_id = Column(Integer, ForeignKey("sources.id"))
    hn_item_id = Column(Integer)
    hn_points = Column(Integer)
    hn_comments = Column(Integer)

    score = Column(Float, nullable=False, default=0.0)

    source = relationship("Source", back_populates="items")
    topics = relationship(
        "ItemTopic", back_populates="item", cascade="all, delete-orphan", lazy="selectin"
    )
    discussions = relationship(
        "ItemDiscussion", back_populates="item", cascade="all, delete-orphan", lazy="selectin"
    )


class ItemTopic(Base):
    __tablename__ = "item_topics"

    item_id = Column(Integer, ForeignKey("items.id"), primary_key=True)
    topic = Column(String(100), primary_key=True)

    item = relationship("Item", back_populates="topics")


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    mode = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="running")
    celery_task_id = Column(String(100))
    cancel_requested_at = Column(DateTime(timezone=True))
    canceled_at = Column(DateTime(timezone=True))
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True))
    total_candidates = Column(Integer, default=0)
    new_items = Column(Integer, default=0)
    error = Column(Text)

class ItemDiscussion(Base):
    __tablename__ = "item_discussions"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    source = Column(String(50), nullable=False)
    thread_id = Column(String(100), nullable=True)
    summary_zh = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    raw_json = Column(JSONB, nullable=True)

    item = relationship("Item", back_populates="discussions")


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String(100), primary_key=True)
    value = Column(JSONB, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
