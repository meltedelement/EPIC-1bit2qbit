import doubleratchet
import cryptography

from doubleratchet import DoubleRatchet, DiffieHellmanRatchet, AEAD, KDF, Header
from cryptography.hazmat.primitives import hashes, hmac
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class DoubleRatchetKDF(KDF):
    @staticmethod
    def derive(key: bytes, data: bytes, length: int) -> bytes:
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=length,
            salt=key,
            info=b"doubleratchet",
        )
        return hkdf.derive(data)


class X25519DiffieHellmanRatchet(DiffieHellmanRatchet):
    @staticmethod
    def generate_keypair() -> tuple[bytes, bytes]:
        private_key = X25519PrivateKey.generate()
        public_key = private_key.public_key()
        return (
            private_key.private_bytes_raw(),
            public_key.public_bytes_raw(),
        )

    @staticmethod
    def dh(private_key: bytes, public_key: bytes) -> bytes:
        priv = X25519PrivateKey.from_private_bytes(private_key)
        pub = X25519PublicKey.from_public_bytes(public_key)
        return priv.exchange(pub)


class AES256GCMAEAD(AEAD):
    NONCE_SIZE = 12  # 96 bits, recommended for GCM
    KEY_SIZE = 32    # 256 bits

    @staticmethod
    def _build_nonce(counter: int) -> bytes:
        return counter.to_bytes(AES256GCMAEAD.NONCE_SIZE, byteorder='big')

    @staticmethod
    def encrypt(key: bytes, plaintext: bytes, associated_data: bytes, counter: int) -> bytes:
        nonce = AES256GCMAEAD._build_nonce(counter)
        cipher = AESGCM(key)
        return cipher.encrypt(nonce, plaintext, associated_data)

    @staticmethod
    def decrypt(key: bytes, ciphertext: bytes, associated_data: bytes, counter: int) -> bytes:
        nonce = AES256GCMAEAD._build_nonce(counter)
        cipher = AESGCM(key)
        return cipher.decrypt(nonce, ciphertext, associated_data)


class DoubleRatchetHeader(Header):
    PUBLIC_KEY_SIZE = 32  # X25519 public key size

    @staticmethod
    def encode(public_key: bytes, prev_chain_length: int, message_number: int) -> bytes:
        return (
            public_key +
            prev_chain_length.to_bytes(4, byteorder='big') +
            message_number.to_bytes(4, byteorder='big')
        )

    @staticmethod
    def decode(header: bytes) -> tuple[bytes, int, int]:
        public_key = header[:DoubleRatchetHeader.PUBLIC_KEY_SIZE]
        prev_chain_length = int.from_bytes(header[32:36], byteorder='big')
        message_number = int.from_bytes(header[36:40], byteorder='big')
        return (public_key, prev_chain_length, message_number)


DoubleRatchet.encrypt_initial_message()


