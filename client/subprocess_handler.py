"""
Crypto subprocess entry point.

Reads newline-delimited JSON requests from stdin, dispatches to crypto_functions,
writes newline-delimited JSON responses to stdout. One request per line, one
response per line. Binary data is base64-encoded in all messages.

Design note: the design document specifies a Unix domain socket transport. This
implementation uses stdin/stdout — equivalent semantics for a synchronous
request/response pattern, portable across Windows and Linux, and simpler for the
C++ spawn-and-communicate pattern. Revisit if bidirectional streaming is needed.

In-memory state: the subprocess holds the raw DEK in memory after unlock_dek or
create_dek. All other state (x3dh state blob, ratchet state) is owned by the C++
layer and passed in with each call.

Spawn from C++:
    python subprocess_handler.py

Then write JSON lines to its stdin and read JSON lines from its stdout.
"""

import asyncio
import base64
import json
import os
import sys

import x3dh
from crypto_functions import (
    DoubleRatchet,
    create_dek,
    create_state,
    dr_configuration,
    rotate_dek,
    unlock_dek,
)
from crypto_functions.x3dh_init import STATE_KWARGS
from crypto_functions.x3dh_state import X3DHState
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from doubleratchet import EncryptedMessage
from doubleratchet import Header as RatchetHeader

_active_dek: bytes | None = None  # pylint: disable=invalid-name
_STATE_AAD = b"X3DH_STATE"
_NONCE_LEN = 12


def _require_dek() -> bytes:
    if _active_dek is None:
        raise RuntimeError("No active session — call unlock_dek or create_dek first")
    return _active_dek


# Codec helpers
def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _unb64(s: str) -> bytes:
    return base64.b64decode(s)


# x3DH state encryption — wraps library state as an AES-256-GCM blob for C++ storage
def _wrap_state(state: x3dh.State, dek: bytes) -> dict:
    state_bytes = json.dumps(state.json).encode()
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = AESGCM(dek).encrypt(nonce, state_bytes, _STATE_AAD)
    return {"nonce": _b64(nonce), "ciphertext": _b64(ciphertext)}


def _unwrap_state(encrypted: dict, dek: bytes) -> X3DHState:
    state_bytes = AESGCM(dek).decrypt(
        _unb64(encrypted["nonce"]),
        _unb64(encrypted["ciphertext"]),
        _STATE_AAD,
    )
    state, _ = X3DHState.from_json(json.loads(state_bytes.decode()), **STATE_KWARGS)
    return state


def _state_response(state: X3DHState, dek: bytes) -> dict:
    """Re-wrap the state, plus a fresh bundle whenever the library re-published.

    The C++ client must re-publish a `bundle` whenever a response carries one;
    otherwise consumed one-time pre keys are never replenished server-side.
    """
    out = {"encrypted_state": _wrap_state(state, dek)}
    bundle = state.pop_published_bundle()
    if bundle is not None:
        out["bundle"] = _serialize_bundle(bundle)
    return out


# x3DH bundle / header serialisation — translates library namedtuples to JSON
def _serialize_bundle(bundle: x3dh.Bundle) -> dict:
    return {
        "identity_key": _b64(bundle.identity_key),
        "signed_pre_key": _b64(bundle.signed_pre_key),
        "signed_pre_key_sig": _b64(bundle.signed_pre_key_sig),
        "pre_keys": [_b64(pk) for pk in bundle.pre_keys],
    }


def _deserialize_bundle(data: dict) -> x3dh.Bundle:
    return x3dh.Bundle(
        identity_key=_unb64(data["identity_key"]),
        signed_pre_key=_unb64(data["signed_pre_key"]),
        signed_pre_key_sig=_unb64(data["signed_pre_key_sig"]),
        pre_keys=tuple(_unb64(pk) for pk in data["pre_keys"]),
    )


def _serialize_x3dh_header(header: x3dh.Header) -> dict:
    return {
        "identity_key": _b64(header.identity_key),
        "ephemeral_key": _b64(header.ephemeral_key),
        "signed_pre_key": _b64(header.signed_pre_key),
        "pre_key": _b64(header.pre_key) if header.pre_key else None,
    }


def _deserialize_x3dh_header(data: dict) -> x3dh.Header:
    return x3dh.Header(
        identity_key=_unb64(data["identity_key"]),
        ephemeral_key=_unb64(data["ephemeral_key"]),
        signed_pre_key=_unb64(data["signed_pre_key"]),
        pre_key=_unb64(data["pre_key"]) if data.get("pre_key") else None,
    )


# Double Ratchet message serialisation
def _serialize_ratchet_message(msg: EncryptedMessage) -> dict:
    return {
        "header": {
            "ratchet_pub": _b64(msg.header.ratchet_pub),
            "sending_chain_length": msg.header.sending_chain_length,
            "previous_sending_chain_length": msg.header.previous_sending_chain_length,
        },
        "ciphertext": _b64(msg.ciphertext),
    }


def _deserialize_ratchet_message(data: dict) -> EncryptedMessage:
    return EncryptedMessage(
        header=RatchetHeader(
            ratchet_pub=_unb64(data["header"]["ratchet_pub"]),
            sending_chain_length=data["header"]["sending_chain_length"],
            previous_sending_chain_length=data["header"]["previous_sending_chain_length"],
        ),
        ciphertext=_unb64(data["ciphertext"]),
    )


# DEK lifecycle handlers
def _handle_create_dek(p: dict) -> dict:
    global _active_dek
    result = create_dek(p["pin"], p["username"])
    _active_dek = _unb64(result["dek_raw"])
    return {"encrypted_dek": result["encrypted_dek"]}


def _handle_unlock_dek(p: dict) -> dict:
    global _active_dek
    _active_dek = _unb64(unlock_dek(p["pin"], p["username"], p["encrypted_dek"]))
    return {}


def _handle_rotate_dek(p: dict) -> dict:
    return {
        "encrypted_dek": rotate_dek(p["old_pin"], p["new_pin"], p["username"], p["encrypted_dek"])
    }


# x3DH handlers
def _handle_create_state(_: dict) -> dict:
    dek = _require_dek()
    state = create_state()
    return {
        "encrypted_state": _wrap_state(state, dek),
        "bundle": _serialize_bundle(state.bundle),
    }


def _handle_get_bundle(p: dict) -> dict:
    dek = _require_dek()
    state = _unwrap_state(p["encrypted_state"], dek)
    return _serialize_bundle(state.bundle)


def _handle_generate_pre_keys(p: dict) -> dict:
    dek = _require_dek()
    state = _unwrap_state(p["encrypted_state"], dek)
    state.generate_pre_keys(p["count"])
    return {
        "encrypted_state": _wrap_state(state, dek),
        "bundle": _serialize_bundle(state.bundle),
    }


def _handle_rotate_signed_pre_key(p: dict) -> dict:
    dek = _require_dek()
    state = _unwrap_state(p["encrypted_state"], dek)
    state.rotate_signed_pre_key()
    return {
        "encrypted_state": _wrap_state(state, dek),
        "bundle": _serialize_bundle(state.bundle),
    }


def _handle_get_num_pre_keys(p: dict) -> dict:
    dek = _require_dek()
    state = _unwrap_state(p["encrypted_state"], dek)
    return {"num_pre_keys": state.get_num_visible_pre_keys()}


def _handle_get_shared_secret_active(p: dict) -> dict:
    dek = _require_dek()
    state = _unwrap_state(p["encrypted_state"], dek)
    shared_secret, ad, header = asyncio.run(
        state.get_shared_secret_active(_deserialize_bundle(p["bob_bundle"]))
    )
    return {
        "shared_secret": _b64(shared_secret),
        "associated_data": _b64(ad),
        "header": _serialize_x3dh_header(header),
        "bob_initial_ratchet_pub": _b64(header.signed_pre_key),
        "encrypted_state": _wrap_state(state, dek),
    }


def _handle_get_shared_secret_passive(p: dict) -> dict:
    dek = _require_dek()
    state = _unwrap_state(p["encrypted_state"], dek)
    shared_secret, ad, spk_pair = asyncio.run(
        state.get_shared_secret_passive(_deserialize_x3dh_header(p["header"]))
    )
    return {
        "shared_secret": _b64(shared_secret),
        "associated_data": _b64(ad),
        "own_ratchet_priv": _b64(spk_pair.priv),
        **_state_response(state, dek),
    }


def _handle_delete_hidden_pre_keys(p: dict) -> dict:
    dek = _require_dek()
    state = _unwrap_state(p["encrypted_state"], dek)
    state.delete_hidden_pre_keys()
    return {"encrypted_state": _wrap_state(state, dek)}


# Double Ratchet handlers
def _handle_encrypt_initial_message(p: dict) -> dict:
    async def run():
        return await DoubleRatchet.encrypt_initial_message(
            shared_secret=_unb64(p["shared_secret"]),
            recipient_ratchet_pub=_unb64(p["recipient_ratchet_pub"]),
            message=_unb64(p["message"]),
            associated_data=_unb64(p["associated_data"]),
            **dr_configuration,
        )

    dr, msg = asyncio.run(run())
    return {"encrypted_message": _serialize_ratchet_message(msg), "ratchet_state": dr.json}


def _handle_decrypt_initial_message(p: dict) -> dict:
    msg = _deserialize_ratchet_message(p["encrypted_message"])

    async def run():
        return await DoubleRatchet.decrypt_initial_message(
            shared_secret=_unb64(p["shared_secret"]),
            own_ratchet_priv=_unb64(p["own_ratchet_priv"]),
            message=msg,
            associated_data=_unb64(p["associated_data"]),
            **dr_configuration,
        )

    dr, plaintext = asyncio.run(run())
    return {"plaintext": _b64(plaintext), "ratchet_state": dr.json}


def _handle_encrypt_message(p: dict) -> dict:
    dr = DoubleRatchet.from_json(p["ratchet_state"], **dr_configuration)

    async def run():
        return await dr.encrypt_message(_unb64(p["message"]), _unb64(p["associated_data"]))

    msg = asyncio.run(run())
    return {"encrypted_message": _serialize_ratchet_message(msg), "ratchet_state": dr.json}


def _handle_decrypt_message(p: dict) -> dict:
    dr = DoubleRatchet.from_json(p["ratchet_state"], **dr_configuration)
    msg = _deserialize_ratchet_message(p["encrypted_message"])

    async def run():
        return await dr.decrypt_message(msg, _unb64(p["associated_data"]))

    plaintext = asyncio.run(run())
    return {"plaintext": _b64(plaintext), "ratchet_state": dr.json}


# Dispatch table and main loop
_DISPATCH: dict[str, callable] = {
    "create_dek": _handle_create_dek,
    "unlock_dek": _handle_unlock_dek,
    "rotate_dek": _handle_rotate_dek,
    "create_state": _handle_create_state,
    "get_bundle": _handle_get_bundle,
    "generate_pre_keys": _handle_generate_pre_keys,
    "rotate_signed_pre_key": _handle_rotate_signed_pre_key,
    "get_num_pre_keys": _handle_get_num_pre_keys,
    "get_shared_secret_active": _handle_get_shared_secret_active,
    "get_shared_secret_passive": _handle_get_shared_secret_passive,
    "delete_hidden_pre_keys": _handle_delete_hidden_pre_keys,
    "encrypt_initial_message": _handle_encrypt_initial_message,
    "decrypt_initial_message": _handle_decrypt_initial_message,
    "encrypt_message": _handle_encrypt_message,
    "decrypt_message": _handle_decrypt_message,
}


def _process(request: dict) -> dict:
    method = request.get("method")
    if method not in _DISPATCH:
        return {"error": f"Unknown method: {method!r}"}
    try:
        return {"result": _DISPATCH[method](request.get("params", {}))}
    except Exception as exc:
        return {"error": str(exc)}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response: dict = {"error": f"Invalid JSON: {exc}"}
        else:
            response = _process(request)
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
