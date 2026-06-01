from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


# Inbound frames (client → server)
class SendMessageFrame(BaseModel):
    type: Literal["send_message"]
    recipient: str = Field(min_length=1, max_length=64)
    ciphertext: str = Field(min_length=1)
    mid: str = Field(min_length=1, max_length=150)


class PublishKeyBundleFrame(BaseModel):
    type: Literal["publish_key_bundle"]
    identity_key: str = Field(min_length=1)
    signed_pre_key: str = Field(min_length=1)
    signed_pre_key_sig: str = Field(min_length=1)
    one_time_pre_keys: list[str] = Field(min_length=1)


class RequestKeyBundleFrame(BaseModel):
    type: Literal["request_key_bundle"]
    target_username: str = Field(min_length=1, max_length=64)


InboundFrame = Annotated[
    Union[SendMessageFrame, PublishKeyBundleFrame, RequestKeyBundleFrame],
    Field(discriminator="type"),
]


# Outbound frames (server → client)
class DeliverMessageFrame(BaseModel):
    type: Literal["deliver_message"] = "deliver_message"
    sender: str
    ciphertext: str
    mid: str


class KeyBundleResponseFrame(BaseModel):
    type: Literal["key_bundle_response"] = "key_bundle_response"
    username: str
    identity_key: str
    signed_pre_key: str
    signed_pre_key_sig: str
    one_time_pre_key: str | None  # None if the OTPK pool is exhausted


class ErrorFrame(BaseModel):
    type: Literal["error"] = "error"
    code: str
    detail: str
