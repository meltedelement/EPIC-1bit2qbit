from pydantic import BaseModel


class RegisterRequest(BaseModel):
    username: str
    auth_key: str  # hex-encoded 32-byte HKDF-derived key, never the raw password
    salt: str      # hex-encoded 32-byte HKDF salt, generated client-side


class RegisterResponse(BaseModel):
    username: str
