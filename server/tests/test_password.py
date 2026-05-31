from backend.crypto.password import hash_password, needs_rehash, verify_password

_PASSWORD = "dont-roll-your-own-crypto"


class TestHashPassword:
    def test_returns_string(self):
        assert isinstance(hash_password(_PASSWORD), str)

    def test_output_is_argon2id(self):
        assert hash_password(_PASSWORD).startswith("$argon2id$")

    def test_unique_hashes(self):
        assert hash_password(_PASSWORD) != hash_password(_PASSWORD)


class TestVerifyPassword:
    def test_correct_password_returns_true(self):
        hashed = hash_password(_PASSWORD)
        assert verify_password(hashed, _PASSWORD) is True

    def test_wrong_password_returns_false(self):
        hashed = hash_password(_PASSWORD)
        assert verify_password(hashed, "wrong-password") is False

    def test_empty_password_returns_false(self):
        hashed = hash_password(_PASSWORD)
        assert verify_password(hashed, "") is False


class TestNeedsRehash:
    def test_fresh_hash_does_not_need_rehash(self):
        assert needs_rehash(hash_password(_PASSWORD)) is False

    def test_outdated_parameters_needs_rehash(self):
        from argon2 import PasswordHasher

        old_ph = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
        old_hash = old_ph.hash(_PASSWORD)
        assert needs_rehash(old_hash) is True
