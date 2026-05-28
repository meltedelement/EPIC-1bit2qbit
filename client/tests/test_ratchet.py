import asyncio
import os
from dataclasses import dataclass

import pytest
from cryptography.exceptions import InvalidTag

from crypto_functions.ratchet import AES256GCMAEAD, DoubleRatchet

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


class TestBuildAssociatedData:
    def test_deterministic(self):
        h = _header()
        assert DoubleRatchet._build_associated_data(_AAD, h) == DoubleRatchet._build_associated_data(_AAD, h)

    def test_length_prefix_is_first_eight_bytes(self):
        ad = b"test"
        result = DoubleRatchet._build_associated_data(ad, _header())
        assert result[:8] == len(ad).to_bytes(8, "big")

    def test_different_ad_gives_different_output(self):
        h = _header()
        assert DoubleRatchet._build_associated_data(b"aaa", h) != DoubleRatchet._build_associated_data(b"bbb", h)

    def test_length_prefix_prevents_aad_collision(self):
        # b"A" + pub starting b"B..." must differ from b"AB" + pub starting b"\x00..."
        # because the 8-byte length prefixes (1 vs 2) keep them distinct.
        r1 = DoubleRatchet._build_associated_data(b"A", _header(pub=b"B" + b"\x00" * 31))
        r2 = DoubleRatchet._build_associated_data(b"AB", _header(pub=b"\x00" * 32))
        assert r1 != r2

    def test_changed_ratchet_pub_gives_different_output(self):
        assert (
            DoubleRatchet._build_associated_data(_AAD, _header(pub=b"\x01" * 32))
            != DoubleRatchet._build_associated_data(_AAD, _header(pub=b"\x02" * 32))
        )

    def test_changed_sending_chain_length_gives_different_output(self):
        assert (
            DoubleRatchet._build_associated_data(_AAD, _header(scl=0))
            != DoubleRatchet._build_associated_data(_AAD, _header(scl=1))
        )

    def test_changed_previous_sending_chain_length_gives_different_output(self):
        assert (
            DoubleRatchet._build_associated_data(_AAD, _header(pscl=0))
            != DoubleRatchet._build_associated_data(_AAD, _header(pscl=1))
        )
