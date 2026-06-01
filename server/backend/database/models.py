from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))  # Argon2id PHC string


class KeyBundle(Base):
    """
    Stores a user's long-lived X3DH keys: identity key, signed prekey, and SPK signature.
    One row per user — overwritten on each signed prekey rotation (every 7 days).
    The server stores but never interprets key material.
    """

    __tablename__ = "key_bundles"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_username: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.username"), unique=True
    )
    identity_key: Mapped[str] = mapped_column(Text)  # base64 Ed25519 public key
    signed_pre_key: Mapped[str] = mapped_column(Text)  # base64 signed prekey
    signed_pre_key_sig: Mapped[str] = mapped_column(Text)  # base64 signature over SPK
    published_at: Mapped[datetime] = mapped_column(DateTime)


class OneTimePreKey(Base):
    """
    Pool of one-time prekeys (OTPKs) for a user's X3DH key bundle.
    Each row is one OTPK. Rows are deleted individually as they are consumed
    by requesters — one OTPK is popped per key bundle request.
    The client replenishes the pool when it drops below threshold.
    """

    __tablename__ = "one_time_pre_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_username: Mapped[str] = mapped_column(String(64), ForeignKey("users.username"))
    key_data: Mapped[str] = mapped_column(Text)  # base64 OTPK
    created_at: Mapped[datetime] = mapped_column(DateTime)

    __table_args__ = (Index("ix_otpk_owner", "owner_username"),)


class BlockchainMessageQueue(Base):
    """
    Staging area for messages awaiting blockchain anchoring.

    A row is written here when a message is sent and removed after the batcher
    successfully submits it to the Sepolia contract.  The effective TTL of a row
    is the edit window — once edit_deadline passes the batcher is free to pick
    it up.

    The server never interprets ciphertext content.  Edits and deletes are
    encoded by the sender inside the ciphertext and are opaque to the server —
    if the same mid arrives again from the same authenticated sender before
    edit_deadline, the ciphertext field is simply overwritten in place.
    """

    __tablename__ = "blockchain_message_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    mid: Mapped[str] = mapped_column(String(150), unique=True)
    sender_username: Mapped[str] = mapped_column(String(64), ForeignKey("users.username"))
    recipient_username: Mapped[str] = mapped_column(String(64), ForeignKey("users.username"))
    ciphertext: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    edit_deadline: Mapped[datetime] = mapped_column(DateTime)

    __table_args__ = (
        # Batcher queries: WHERE edit_deadline < NOW()
        Index("ix_bmq_edit_deadline", "edit_deadline"),
    )


class TTLDeliveryQueue(Base):
    """
    Offline delivery queue for frames that could not be pushed to a live session.

    All rows are deliver_message frames — the server never distinguishes new
    messages from ciphertext updates.  If a mid is updated while the recipient
    is offline, both the original frame and the update frame are appended; the
    client reconciles them in created_at order on reconnect.

    Rows are hard-deleted in one of two ways:
      - immediately on successful delivery when the recipient reconnects
      - by the TTL daemon once expires_at passes, for frames never delivered
    """

    __tablename__ = "ttl_delivery_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient_username: Mapped[str] = mapped_column(String(64), ForeignKey("users.username"))
    frame_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)

    __table_args__ = (
        # Offline drain: WHERE recipient_username = ? ORDER BY created_at
        Index("ix_tdq_recipient", "recipient_username"),
        # TTL daemon: WHERE expires_at < NOW()
        Index("ix_tdq_expires", "expires_at"),
    )
