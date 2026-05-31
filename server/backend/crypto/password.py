from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# RFC 9106 parameters for memory-constrained environments: t=3, m=64 MiB.
# OWASP minimum is m=12 MiB, t=3. Parallelism does not affect security.
# We only have 2 cores, so we set it to 1.
_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1)

def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(hashed: str, password: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    return _ph.check_needs_rehash(hashed)
