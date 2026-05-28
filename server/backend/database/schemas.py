from pydantic import BaseModel, Field

_HEX_64 = Field(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    auth_key: str = (
        _HEX_64  # hex-encoded 32-byte HKDF-derived key, never the raw password
    )
    salt: str = _HEX_64  # hex-encoded 32-byte HKDF salt, generated client-side


class RegisterResponse(BaseModel):
    username: str
