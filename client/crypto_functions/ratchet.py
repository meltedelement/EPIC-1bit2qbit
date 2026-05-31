import os
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

    All methods accept **dr_configuration as keyword arguments. Use the
    module-level dr_configuration dict for convenience.

    Session setup (classmethods):
        encrypt_initial_message(
            shared_secret, recipient_ratchet_pub, message, associated_data,
            **dr_configuration) -> (DoubleRatchet, EncryptedMessage)
        decrypt_initial_message(
            shared_secret, own_ratchet_priv, message, associated_data,
            **dr_configuration) -> (DoubleRatchet, bytes)

    Messaging (instance methods):
        encrypt_message(message, associated_data) -> EncryptedMessage
        decrypt_message(message, associated_data) -> bytes

    Serialization:
        dr.json                          -> JSON-serializable state dict
        from_json(serialized, **dr_configuration) -> DoubleRatchet
    """

    @staticmethod
    def _build_associated_data(associated_data: bytes, header: Header) -> bytes:
        return (
            len(associated_data).to_bytes(8, "big")
            + associated_data
            + header.ratchet_pub
            + header.sending_chain_length.to_bytes(8, "big")
            + header.previous_sending_chain_length.to_bytes(8, "big")
        )


class DiffieHellmanRatchet(dhr25519.DiffieHellmanRatchet):
    """X25519-based Diffie-Hellman ratchet for ephemeral key exchange.
    Used internally via dr_configuration.
    """


class RootChainKDF(kdf_hkdf.KDF):
    """HKDF-based KDF for the root chain. Advances during DH ratchet steps.
    Used internally via dr_configuration.
    """

    @staticmethod
    def _get_hash_function() -> HashFunction:
        return HashFunction.SHA_256

    @staticmethod
    def _get_info() -> bytes:
        return b"EPIC Root Chain KDF"


class MessageChainKDF(kdf_separate_hmacs.KDF):
    """HMAC-based KDF for the message chain. Derives unique keys per message.
    Used internally via dr_configuration.
    """

    @staticmethod
    def _get_hash_function() -> HashFunction:
        return HashFunction.SHA_256


class AES256GCMAEAD:
    """
    AES-256-GCM authenticated encryption. Used internally via dr_configuration.

    Can also be used standalone:
        encrypt(plaintext, key, associated_data) -> bytes  (nonce prepended)
        decrypt(ciphertext, key, associated_data) -> bytes

    Key must be exactly 32 bytes. Nonce is 12-byte random, prepended to ciphertext.
    """

    NONCE_SIZE = 12
    KEY_SIZE = 32
    TAG_SIZE = 16

    @staticmethod
    def _check_key(key: bytes) -> None:
        if len(key) != AES256GCMAEAD.KEY_SIZE:
            raise ValueError("Invalid key length (expected 32 bytes for AES-256)")

    @staticmethod
    async def encrypt(plaintext: bytes, key: bytes, associated_data: bytes) -> bytes:
        AES256GCMAEAD._check_key(key)

        nonce = os.urandom(AES256GCMAEAD.NONCE_SIZE)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, associated_data)

        return nonce + ciphertext

    @staticmethod
    async def decrypt(ciphertext: bytes, key: bytes, associated_data: bytes) -> bytes:
        if len(ciphertext) < AES256GCMAEAD.NONCE_SIZE + AES256GCMAEAD.TAG_SIZE:
            raise ValueError("Ciphertext too short (missing nonce or GCM tag)")

        AES256GCMAEAD._check_key(key)

        nonce = ciphertext[: AES256GCMAEAD.NONCE_SIZE]
        ct = ciphertext[AES256GCMAEAD.NONCE_SIZE :]

        return AESGCM(key).decrypt(nonce, ct, associated_data)


# Configuration dictionary for DoubleRatchet initialization.
# Pass to encrypt_initial_message, decrypt_initial_message, and from_json using **dr_configuration
dr_configuration: Dict[str, Any] = {
    "diffie_hellman_ratchet_class": DiffieHellmanRatchet,
    "root_chain_kdf": RootChainKDF,
    "message_chain_kdf": MessageChainKDF,
    "message_chain_constant": b"\x01\x02",
    "dos_protection_threshold": 100,
    "max_num_skipped_message_keys": 100,
    "aead": AES256GCMAEAD,
}

