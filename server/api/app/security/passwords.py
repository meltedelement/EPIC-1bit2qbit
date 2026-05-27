from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher()


def store_auth_key(auth_key: str) -> str:
    return _ph.hash(auth_key)


def verify_auth_key(auth_key: str, stored: str) -> bool:
    try:
        return _ph.verify(stored, auth_key)
    except VerifyMismatchError:
        return False
