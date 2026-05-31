from ..crypto.password import hash_password, verify_password
from ..database.db import SessionLocal
from ..database.models import User

# Pre-hashed dummy used to equalise timing when the username does not exist,
# preventing username enumeration via response-time differences.
_DUMMY_HASH = hash_password("dummy")


def verify_credentials(username: str, password: str) -> bool:
    """DB lookup + Argon2 verify — runs in a worker thread."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        target_hash = user.password_hash if user is not None else _DUMMY_HASH
        ok = verify_password(target_hash, password)
        return user is not None and ok
    finally:
        db.close()
