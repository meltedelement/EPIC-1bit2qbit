from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    auth_key: Mapped[str] = mapped_column(String(255))  # Argon2id PHC string
    salt: Mapped[str] = mapped_column(String(64))  # hex-encoded 32-byte HKDF salt, client-generated
