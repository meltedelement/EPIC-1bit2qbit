"""Password handling boundary — placeholder.

Currently a plaintext compare so the register/login flow is end-to-end
functional. The crypto teammate will swap these two functions for the
agreed hash (Argon2id / PBKDF2-HMAC-SHA256) without route code changing.
"""


def hash_password(password: str) -> str:
    return password


def verify_password(password: str, stored: str) -> bool:
    return password == stored
