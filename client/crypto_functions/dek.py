import base64
import os

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Argon2id parameters for client-side KEK derivation from the encryption PIN.
# Sourced from RFC 9106 Section 4 — "Key derivation for hard-drive encryption,
# which takes 3 seconds on a 2 GHz CPU using 2 cores — Argon2id with 4 lanes
# and 6 GiB of RAM."  t=1 is sufficient because a single pass over 6 GiB of
# memory already meets the 3-second target; increasing t further would exceed it.
_ARGON2_TIME_COST = 1
_ARGON2_MEMORY_COST = 6_291_456  # 6 GiB in KiB (6 * 1024 * 1024)
_ARGON2_PARALLELISM = 4
_ARGON2_HASH_LEN = 32
_ARGON2_SALT_LEN = 32

_AES_NONCE_LEN = 12


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _unb64(s: str) -> bytes:
    return base64.b64decode(s)


def _derive_kek(pin: str, salt: bytes) -> bytes:
    return hash_secret_raw(
        secret=pin.encode(),
        salt=salt,
        time_cost=_ARGON2_TIME_COST,
        memory_cost=_ARGON2_MEMORY_COST,
        parallelism=_ARGON2_PARALLELISM,
        hash_len=_ARGON2_HASH_LEN,
        type=Type.ID,
    )


def create_dek(pin: str, username: str) -> dict:
    """
    Generate a fresh DEK at registration. Called once per account on this device.

    Returns:
        encrypted_dek  — { salt, nonce, ciphertext } all base64;
                          store in DB via C++ layer
        dek_raw        — base64 raw DEK for this session;
                          keep in subprocess memory, never write to disk

    Username is bound as AAD so the same encrypted blob cannot be
    transplanted to a different account.
    """
    salt = os.urandom(_ARGON2_SALT_LEN)
    dek = os.urandom(32)
    kek = _derive_kek(pin, salt)
    nonce = os.urandom(_AES_NONCE_LEN)
    ciphertext = AESGCM(kek).encrypt(nonce, dek, username.encode())

    return {
        "encrypted_dek": {
            "salt": _b64(salt),
            "nonce": _b64(nonce),
            "ciphertext": _b64(ciphertext),
        },
        "dek_raw": _b64(dek),
    }


def unlock_dek(pin: str, username: str, encrypted_dek: dict) -> str:
    """
    Re-derive KEK from PIN and decrypt the stored DEK. Called at login.

    Returns the raw DEK as base64 for the current session.
    Raises ValueError on wrong PIN or tampered ciphertext.
    """
    salt = _unb64(encrypted_dek["salt"])
    nonce = _unb64(encrypted_dek["nonce"])
    ciphertext = _unb64(encrypted_dek["ciphertext"])
    kek = _derive_kek(pin, salt)

    try:
        dek = AESGCM(kek).decrypt(nonce, ciphertext, username.encode())
    except InvalidTag as exc:
        raise ValueError("DEK decryption failed — incorrect PIN or corrupted key store") from exc

    return _b64(dek)


def rotate_dek(old_pin: str, new_pin: str, username: str, encrypted_dek: dict) -> dict:
    """
    Re-wrap the DEK under a new KEK when the user changes their encryption PIN.

    The DEK itself is unchanged — only the wrapping key rotates, so no private key
    material needs to be re-encrypted. A fresh salt and nonce are generated for the
    new wrapping to ensure the new KEK is independent of the old one.

    Returns a new encrypted_dek blob for the C++ layer to update in the DB.
    """
    salt = _unb64(encrypted_dek["salt"])
    nonce = _unb64(encrypted_dek["nonce"])
    ciphertext = _unb64(encrypted_dek["ciphertext"])
    old_kek = _derive_kek(old_pin, salt)

    try:
        dek = AESGCM(old_kek).decrypt(nonce, ciphertext, username.encode())
    except InvalidTag as exc:
        raise ValueError(
            "DEK decryption failed — incorrect old PIN or corrupted key store"
        ) from exc

    new_salt = os.urandom(_ARGON2_SALT_LEN)
    new_kek = _derive_kek(new_pin, new_salt)
    new_nonce = os.urandom(_AES_NONCE_LEN)
    new_ciphertext = AESGCM(new_kek).encrypt(new_nonce, dek, username.encode())

    return {
        "salt": _b64(new_salt),
        "nonce": _b64(new_nonce),
        "ciphertext": _b64(new_ciphertext),
    }
