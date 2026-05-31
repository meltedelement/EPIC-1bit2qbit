import asyncio
import os
from dataclasses import dataclass

import pytest
from crypto_functions.ratchet import AES256GCMAEAD, DoubleRatchet, dr_configuration
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

_PLAINTEXT = b"hello world"
_AAD = b"associated data"


@dataclass
class _Header:
    ratchet_pub: bytes
    sending_chain_length: int
    previous_sending_chain_length: int


def _header(pub=None, scl=0, pscl=0):
    return _Header(
        ratchet_pub=pub if pub is not None else b"\x01" * 32,
        sending_chain_length=scl,
        previous_sending_chain_length=pscl,
    )


class TestAES256GCMAEADRoundtrip:
    def test_decrypt_recovers_plaintext(self):
        key = os.urandom(32)
        ct = asyncio.run(AES256GCMAEAD.encrypt(_PLAINTEXT, key, _AAD))
        assert asyncio.run(AES256GCMAEAD.decrypt(ct, key, _AAD)) == _PLAINTEXT

    def test_nonce_is_randomised(self):
        key = os.urandom(32)
        ct1 = asyncio.run(AES256GCMAEAD.encrypt(_PLAINTEXT, key, _AAD))
        ct2 = asyncio.run(AES256GCMAEAD.encrypt(_PLAINTEXT, key, _AAD))
        assert ct1 != ct2

    def test_empty_plaintext_roundtrip(self):
        key = os.urandom(32)
        ct = asyncio.run(AES256GCMAEAD.encrypt(b"", key, _AAD))
        assert asyncio.run(AES256GCMAEAD.decrypt(ct, key, _AAD)) == b""

    def test_empty_aad_roundtrip(self):
        key = os.urandom(32)
        ct = asyncio.run(AES256GCMAEAD.encrypt(_PLAINTEXT, key, b""))
        assert asyncio.run(AES256GCMAEAD.decrypt(ct, key, b"")) == _PLAINTEXT


class TestAES256GCMAEADTamperDetection:
    def test_modified_ciphertext_raises(self):
        key = os.urandom(32)
        ct = bytearray(asyncio.run(AES256GCMAEAD.encrypt(_PLAINTEXT, key, _AAD)))
        ct[-1] ^= 0xFF
        with pytest.raises(InvalidTag):
            asyncio.run(AES256GCMAEAD.decrypt(bytes(ct), key, _AAD))

    def test_modified_nonce_raises(self):
        key = os.urandom(32)
        ct = bytearray(asyncio.run(AES256GCMAEAD.encrypt(_PLAINTEXT, key, _AAD)))
        ct[0] ^= 0xFF
        with pytest.raises(InvalidTag):
            asyncio.run(AES256GCMAEAD.decrypt(bytes(ct), key, _AAD))

    def test_modified_aad_raises(self):
        key = os.urandom(32)
        ct = asyncio.run(AES256GCMAEAD.encrypt(_PLAINTEXT, key, _AAD))
        with pytest.raises(InvalidTag):
            asyncio.run(AES256GCMAEAD.decrypt(ct, key, b"wrong aad"))

    def test_wrong_key_raises(self):
        key = os.urandom(32)
        ct = asyncio.run(AES256GCMAEAD.encrypt(_PLAINTEXT, key, _AAD))
        with pytest.raises(InvalidTag):
            asyncio.run(AES256GCMAEAD.decrypt(ct, os.urandom(32), _AAD))


class TestAES256GCMAEADKeyValidation:
    def test_short_key_encrypt_raises(self):
        with pytest.raises(ValueError, match="32 bytes"):
            asyncio.run(AES256GCMAEAD.encrypt(_PLAINTEXT, b"tooshort", _AAD))

    def test_long_key_encrypt_raises(self):
        with pytest.raises(ValueError, match="32 bytes"):
            asyncio.run(AES256GCMAEAD.encrypt(_PLAINTEXT, os.urandom(33), _AAD))

    def test_short_key_decrypt_raises(self):
        key = os.urandom(32)
        ct = asyncio.run(AES256GCMAEAD.encrypt(_PLAINTEXT, key, _AAD))
        with pytest.raises(ValueError, match="32 bytes"):
            asyncio.run(AES256GCMAEAD.decrypt(ct, b"tooshort", _AAD))

    def test_ciphertext_too_short_raises(self):
        key = os.urandom(32)
        with pytest.raises(ValueError, match="too short"):
            asyncio.run(AES256GCMAEAD.decrypt(b"\x00" * 5, key, _AAD))


class TestBuildAssociatedData:  # pylint: disable=protected-access
    def test_deterministic(self):
        h = _header()
        assert DoubleRatchet._build_associated_data(
            _AAD, h
        ) == DoubleRatchet._build_associated_data(_AAD, h)

    def test_length_prefix_is_first_eight_bytes(self):
        ad = b"test"
        result = DoubleRatchet._build_associated_data(ad, _header())
        assert result[:8] == len(ad).to_bytes(8, "big")

    def test_different_ad_gives_different_output(self):
        h = _header()
        assert DoubleRatchet._build_associated_data(
            b"aaa", h
        ) != DoubleRatchet._build_associated_data(b"bbb", h)

    def test_length_prefix_prevents_aad_collision(self):
        # b"A" + pub starting b"B..." must differ from b"AB" + pub starting b"\x00..."
        # because the 8-byte length prefixes (1 vs 2) keep them distinct.
        r1 = DoubleRatchet._build_associated_data(b"A", _header(pub=b"B" + b"\x00" * 31))
        r2 = DoubleRatchet._build_associated_data(b"AB", _header(pub=b"\x00" * 32))
        assert r1 != r2

    def test_changed_ratchet_pub_gives_different_output(self):
        assert DoubleRatchet._build_associated_data(
            _AAD, _header(pub=b"\x01" * 32)
        ) != DoubleRatchet._build_associated_data(_AAD, _header(pub=b"\x02" * 32))

    def test_changed_sending_chain_length_gives_different_output(self):
        assert DoubleRatchet._build_associated_data(
            _AAD, _header(scl=0)
        ) != DoubleRatchet._build_associated_data(_AAD, _header(scl=1))

    def test_changed_previous_sending_chain_length_gives_different_output(self):
        assert DoubleRatchet._build_associated_data(
            _AAD, _header(pscl=0)
        ) != DoubleRatchet._build_associated_data(_AAD, _header(pscl=1))


async def _setup_session():
    """Simulate a post-X3DH session.
    Shared secret agreed externally; Bob supplies his ratchet pub key.
    """
    shared_secret = os.urandom(32)
    bob_ratchet_priv = X25519PrivateKey.generate()

    alice_dr, initial_message = await DoubleRatchet.encrypt_initial_message(
        shared_secret=shared_secret,
        recipient_ratchet_pub=bob_ratchet_priv.public_key().public_bytes_raw(),
        message=_PLAINTEXT,
        associated_data=_AAD,
        **dr_configuration,
    )
    bob_dr, _ = await DoubleRatchet.decrypt_initial_message(
        shared_secret=shared_secret,
        own_ratchet_priv=bob_ratchet_priv.private_bytes_raw(),
        message=initial_message,
        associated_data=_AAD,
        **dr_configuration,
    )
    return alice_dr, bob_dr


class TestDoubleRatchetEndToEnd:
    def test_initial_message_decrypted_correctly(self):
        shared_secret = os.urandom(32)
        bob_ratchet_priv = X25519PrivateKey.generate()

        async def run():
            _, initial_message = await DoubleRatchet.encrypt_initial_message(
                shared_secret=shared_secret,
                recipient_ratchet_pub=bob_ratchet_priv.public_key().public_bytes_raw(),
                message=_PLAINTEXT,
                associated_data=_AAD,
                **dr_configuration,
            )
            _, plaintext = await DoubleRatchet.decrypt_initial_message(
                shared_secret=shared_secret,
                own_ratchet_priv=bob_ratchet_priv.private_bytes_raw(),
                message=initial_message,
                associated_data=_AAD,
                **dr_configuration,
            )
            return plaintext

        assert asyncio.run(run()) == _PLAINTEXT

    def test_alice_to_bob(self):
        async def run():
            alice_dr, bob_dr = await _setup_session()
            encrypted = await alice_dr.encrypt_message(b"hello bob", _AAD)
            return await bob_dr.decrypt_message(encrypted, _AAD)

        assert asyncio.run(run()) == b"hello bob"

    def test_bob_to_alice(self):
        async def run():
            alice_dr, bob_dr = await _setup_session()
            encrypted = await bob_dr.encrypt_message(b"hello alice", _AAD)
            return await alice_dr.decrypt_message(encrypted, _AAD)

        assert asyncio.run(run()) == b"hello alice"

    def test_multi_message_conversation(self):
        async def run():
            alice_dr, bob_dr = await _setup_session()
            results = []
            for i in range(5):
                enc = await alice_dr.encrypt_message(f"alice msg {i}".encode(), _AAD)
                results.append(await bob_dr.decrypt_message(enc, _AAD))
            for i in range(5):
                enc = await bob_dr.encrypt_message(f"bob msg {i}".encode(), _AAD)
                results.append(await alice_dr.decrypt_message(enc, _AAD))
            return results

        results = asyncio.run(run())
        assert results == [f"alice msg {i}".encode() for i in range(5)] + [
            f"bob msg {i}".encode() for i in range(5)
        ]

    def test_out_of_order_messages(self):
        async def run():
            alice_dr, bob_dr = await _setup_session()
            enc1 = await alice_dr.encrypt_message(b"msg 1", _AAD)
            enc2 = await alice_dr.encrypt_message(b"msg 2", _AAD)
            enc3 = await alice_dr.encrypt_message(b"msg 3", _AAD)
            r3 = await bob_dr.decrypt_message(enc3, _AAD)
            r1 = await bob_dr.decrypt_message(enc1, _AAD)
            r2 = await bob_dr.decrypt_message(enc2, _AAD)
            return r1, r2, r3

        r1, r2, r3 = asyncio.run(run())
        assert r1 == b"msg 1"
        assert r2 == b"msg 2"
        assert r3 == b"msg 3"
