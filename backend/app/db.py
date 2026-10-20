import json
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Integer, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Mapped, mapped_column
from .config import DB_URL

engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False, "timeout": 30} if DB_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()
now = lambda: datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))

class Session(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(64))
    mime: Mapped[str] = mapped_column(String(50))
    size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|processing|needs_review|completed|failed
    method: Mapped[str] = mapped_column(String(30), default="")        # pdf-text|ocr
    provider: Mapped[str] = mapped_column(String(30), default="")      # rules|groq
    extracted: Mapped[str] = mapped_column(Text, default="{}")         # original extraction, never overwritten by edits
    corrected: Mapped[str] = mapped_column(Text, default="{}")         # user corrections only
    warnings: Mapped[str] = mapped_column(Text, default="[]")
    error: Mapped[str] = mapped_column(Text, default="")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def effective(self):
        return {**json.loads(self.extracted), **json.loads(self.corrected)}
