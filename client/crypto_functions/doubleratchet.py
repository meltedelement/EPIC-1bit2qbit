import os
import struct
import threading
from typing import Any, Dict

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from doubleratchet import DoubleRatchet as DR
from doubleratchet import Header
from doubleratchet.recommended import HashFunction
from doubleratchet.recommended import diffie_hellman_ratchet_curve25519 as dhr25519
from doubleratchet.recommended import kdf_hkdf, kdf_separate_hmacs


class DoubleRatchet(DR):
    """
    Double Ratchet implementation with custom associated data construction.
    Binds ciphertext to the message header to prevent tampering.
    """

    @staticmethod
    def _build_associated_data(associated_data: bytes, header: Header) -> bytes:
        return (
            associated_data
            + header.ratchet_pub
            + header.sending_chain_length.to_bytes(8, "big")
            + header.previous_sending_chain_length.to_bytes(8, "big")
        )


class DiffieHellmanRatchet(dhr25519.DiffieHellmanRatchet):
    """X25519-based Diffie-Hellman ratchet for ephemeral key exchange."""

    pass


class RootChainKDF(kdf_hkdf.KDF):
    """HKDF-based KDF for the root chain. Advances during DH ratchet steps."""

    @staticmethod
    def _get_hash_function() -> HashFunction:
        return HashFunction.SHA_256

    @staticmethod
    def _get_info() -> bytes:
        return b"EPIC Root Chain KDF"


class MessageChainKDF(kdf_separate_hmacs.KDF):
    """HMAC-based KDF for the message chain. Derives unique keys per message."""

    @staticmethod
    def _get_hash_function() -> HashFunction:
        return HashFunction.SHA_256


class AES256GCMAEAD:
    """
    AES-256-GCM authenticated encryption.

    Nonce format:
        4-byte random prefix || 8-byte counter (NIST recommendation)
    """

    NONCE_SIZE = 12
    KEY_SIZE = 32

    _PREFIX = os.urandom(4)
    _COUNTER = 0
    _COUNTER_MAX = (1 << 64) - 1
    _LOCK = threading.Lock()

    @staticmethod
    def _check_key(key: bytes) -> None:
        if len(key) != AES256GCMAEAD.KEY_SIZE:
            raise ValueError("Invalid key length (expected 32 bytes for AES-256)")

    @classmethod
    def _next_nonce(cls) -> bytes:
        with cls._LOCK:
            nonce = cls._PREFIX + struct.pack(">Q", cls._COUNTER)
            if cls._COUNTER == cls._COUNTER_MAX:
                 cls._PREFIX = os.urandom(4)
                 cls._COUNTER = 0
            else:
                 cls._COUNTER += 1
        return nonce

    @staticmethod
    async def encrypt(plaintext: bytes, key: bytes, associated_data: bytes) -> bytes:
        AES256GCMAEAD._check_key(key)
        nonce = AES256GCMAEAD._next_nonce()
        return nonce + AESGCM(key).encrypt(nonce, plaintext, associated_data)

    @staticmethod
    async def decrypt(ciphertext: bytes, key: bytes, associated_data: bytes) -> bytes:
        if len(ciphertext) < AES256GCMAEAD.NONCE_SIZE + 16:
            raise ValueError("Ciphertext too short (missing nonce or GCM tag)")

        AES256GCMAEAD._check_key(key)
        nonce = ciphertext[: AES256GCMAEAD.NONCE_SIZE]
        return AESGCM(key).decrypt(
             nonce,
             ciphertext[AES256GCMAEAD.NONCE_SIZE :],
             associated_data,
         )


# Configuration dictionary for DoubleRatchet initialization.
# Pass to encrypt_initial_message, decrypt_initial_message, and from_json using **dr_configuration
dr_configuration: Dict[str, Any] = {
    "diffie_hellman_ratchet_class": DiffieHellmanRatchet,
    "root_chain_kdf": RootChainKDF,
    "message_chain_kdf": MessageChainKDF,
    "message_chain_constant": b"\x01\x02",
    "dos_protection_threshold": 100,
    "max_num_skipped_message_keys": 1000,
    "aead": AES256GCMAEAD,
}


# Example usage:
#
# from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
# from cryptography.hazmat.primitives import serialization
#
# async def create_double_ratchets(message: bytes, shared_secret: bytes, ad: bytes):
#     # Bob generates his ratchet key pair
#     bob_ratchet_priv = X25519PrivateKey.generate()
#     bob_ratchet_pub = bob_ratchet_priv.public_key()
#
#     # Alice creates her Double Ratchet by encrypting the initial message for Bob
#     alice_dr, initial_message_encrypted = await DoubleRatchet.encrypt_initial_message(
#         shared_secret=shared_secret,
#         recipient_ratchet_pub=bob_ratchet_pub.public_bytes_raw(),
#         message=message,
#         associated_data=ad,
#         **dr_configuration
#     )
#
#     # Bob creates his Double Ratchet by decrypting the initial message from Alice
#     bob_dr, initial_message_decrypted = await DoubleRatchet.decrypt_initial_message(
#         shared_secret=shared_secret,
#         own_ratchet_priv=bob_ratchet_priv.private_bytes_raw(),
#         message=initial_message_encrypted,
#         associated_data=ad,
#         **dr_configuration
#     )
#
#     # Subsequent messages use encrypt_message/decrypt_message
#     # encrypted = await alice_dr.encrypt_message(b"Hello Bob", ad)
#     # decrypted = await bob_dr.decrypt_message(encrypted, ad)
#
#     return alice_dr, bob_dr
