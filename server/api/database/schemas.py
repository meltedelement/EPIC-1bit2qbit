from pydantic import BaseModel


class RegisterRequest(BaseModel):
    username: str
    auth_key: str  # hex-encoded 32-byte HKDF-derived key, never the raw password


class RegisterResponse(BaseModel):
    username: str
