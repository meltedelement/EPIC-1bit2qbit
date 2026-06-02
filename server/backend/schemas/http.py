from pydantic import BaseModel, Field

_USERNAME_PATTERN = r"^[a-zA-Z0-9_.-]+$"


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=_USERNAME_PATTERN)
    password: str = Field(min_length=1, max_length=256)


class RegisterResponse(BaseModel):
    username: str


class LoginFrame(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=_USERNAME_PATTERN)
    password: str = Field(min_length=1, max_length=256)
