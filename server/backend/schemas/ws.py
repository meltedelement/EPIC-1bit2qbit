from __future__ import annotations

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
    bundle: str = Field(min_length=1)  # opaque JSON blob validated on publish


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
    bundle: str  # the opaque JSON blob stored at publish time


class ErrorFrame(BaseModel):
    type: Literal["error"] = "error"
    code: str
    detail: str
