from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher()


def hash_password(auth_key: str) -> str:
    return _ph.hash(auth_key)


def verify_password(auth_key: str, stored: str) -> bool:
    try:
        return _ph.verify(stored, auth_key)
    except VerifyMismatchError:
        return False


def rehash_if_needed(auth_key: str, stored: str) -> str | None:
    """Return a fresh hash if the stored one was made with weaker params, else None."""
    if _ph.check_needs_rehash(stored):
        return _ph.hash(auth_key)
    return None
