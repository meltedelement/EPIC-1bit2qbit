import x3dh

IDENTITY_KEY_FORMAT = x3dh.IdentityKeyFormat.ED_25519
HASH_FUNCTION = x3dh.HashFunction.SHA_256
INFO = b"EPIC"
SIGNED_PRE_KEY_ROTATION_PERIOD = 604800  # 7 days in seconds
OPK_REFILL_THRESHOLD = 99
OPK_REFILL_TARGET = 100

# Shared kwargs for State.create and State.from_json — single source of truth
STATE_KWARGS = {
    "identity_key_format": IDENTITY_KEY_FORMAT,
    "hash_function": HASH_FUNCTION,
    "info": INFO,
    "signed_pre_key_rotation_period": SIGNED_PRE_KEY_ROTATION_PERIOD,
    "pre_key_refill_threshold": OPK_REFILL_THRESHOLD,
    "pre_key_refill_target": OPK_REFILL_TARGET,
}


def create_state() -> x3dh.State:
    """Create a new X3DH state at registration."""
    return x3dh.State.create(**STATE_KWARGS)
