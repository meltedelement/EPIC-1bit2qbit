from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))  # Argon2id PHC string


class KeyBundle(Base):
    """
    Stores each user's published X3DH key bundle as an opaque JSON blob.
    One bundle per user — publishing a new bundle overwrites the existing one.
    The server validates the bundle structure on publish but never interprets key material.
    """

    __tablename__ = "key_bundles"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_username: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.username"), unique=True, index=True
    )
    bundle_data: Mapped[str] = mapped_column(Text)  # JSON: IK, SPK, OPKs, signature, TTL
    published_at: Mapped[datetime] = mapped_column(DateTime)


class BlockchainMessageQueue(Base):
    """
    Staging area for messages awaiting blockchain anchoring.

    A row is written here when a message is sent and removed after the batcher
    successfully submits it to the Sepolia contract.  The effective TTL of a row
    is the edit window — once edit_deadline passes the batcher is free to pick
    it up.

    ciphertext is NULL and deleted=True for deletion tombstones; the batcher
    hashes the mid alone in that case.
    """

    __tablename__ = "blockchain_message_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    mid: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    sender_username: Mapped[str] = mapped_column(String(64), ForeignKey("users.username"))
    recipient_username: Mapped[str] = mapped_column(String(64), ForeignKey("users.username"))
    ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    edit_deadline: Mapped[datetime] = mapped_column(DateTime)

    __table_args__ = (
        # Batcher queries: WHERE edit_deadline < NOW()
        Index("ix_bmq_edit_deadline", "edit_deadline"),
    )


class TTLDeliveryQueue(Base):
    """
    Offline delivery queue for frames that could not be pushed to a live session.

    Covers three frame types:
      - new messages (receiver was offline at send time)
      - edit notifications (message already delivered, receiver now offline)
      - delete notifications (message already delivered, receiver now offline)

    Frames are append-only — rows are never updated, only inserted or deleted.
    The receiver drains all frames in created_at order on reconnect; the client
    reconciles state (original → edit/delete) locally.

    Rows are hard-deleted by the TTL daemon once expires_at passes.
    """

    __tablename__ = "ttl_delivery_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient_username: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.username"), index=True
    )
    frame_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        # Offline drain: WHERE recipient_username = ? AND delivered_at IS NULL ORDER BY created_at
        Index("ix_tdq_recipient_undelivered", "recipient_username", "delivered_at"),
        # TTL daemon: WHERE expires_at < NOW() AND delivered_at IS NULL
        Index("ix_tdq_expires", "expires_at"),
    )
