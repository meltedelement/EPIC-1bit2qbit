from typing import Any, Dict

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from doubleratchet import DoubleRatchet as DR, Header
from doubleratchet.recommended import (
    diffie_hellman_ratchet_curve25519 as dhr25519,
    HashFunction,
    kdf_hkdf,
    kdf_separate_hmacs,
)


class DoubleRatchet(DR):
    @staticmethod
    def _build_associated_data(associated_data: bytes, header: Header) -> bytes:
        return (
            associated_data
            + header.ratchet_pub
            + header.sending_chain_length.to_bytes(8, "big")
            + header.previous_sending_chain_length.to_bytes(8, "big")
        )


class DiffieHellmanRatchet(dhr25519.DiffieHellmanRatchet):
    pass


class RootChainKDF(kdf_hkdf.KDF):
    @staticmethod
    def _get_hash_function() -> HashFunction:
        return HashFunction.SHA_256

    @staticmethod
    def _get_info() -> bytes:
        return b"EPIC Root Chain KDF"


class MessageChainKDF(kdf_separate_hmacs.KDF):
    @staticmethod
    def _get_hash_function() -> HashFunction:
        return HashFunction.SHA_256


class AES256GCMAEAD:
    NONCE_SIZE = 12
    KEY_SIZE = 32
    NONCE = b"\x00" * 12  # Fixed nonce; safe because Double Ratchet uses unique keys per message

    @staticmethod
    async def encrypt(plaintext: bytes, key: bytes, associated_data: bytes) -> bytes:
        cipher = AESGCM(key)
        return cipher.encrypt(AES256GCMAEAD.NONCE, plaintext, associated_data)

    @staticmethod
    async def decrypt(ciphertext: bytes, key: bytes, associated_data: bytes) -> bytes:
        cipher = AESGCM(key)
        return cipher.decrypt(AES256GCMAEAD.NONCE, ciphertext, associated_data)


dr_configuration: Dict[str, Any] = {
    "diffie_hellman_ratchet_class": DiffieHellmanRatchet,
    "root_chain_kdf": RootChainKDF,
    "message_chain_kdf": MessageChainKDF,
    "message_chain_constant": b"\x01\x02",
    "dos_protection_threshold": 100,
    "max_num_skipped_message_keys": 1000,
    "aead": AES256GCMAEAD,
}
