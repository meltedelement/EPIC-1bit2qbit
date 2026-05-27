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
