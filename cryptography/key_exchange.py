from typing import Any, Dict

from x3dh import Bundle, HashFunction, Header, IdentityKeyFormat, State


class X3DHState(State):
    """X3DH state management for establishing shared secrets."""

    @staticmethod
    def _encode_public_key(
        identity_key_format: IdentityKeyFormat, public_key: bytes
    ) -> bytes:
        return public_key

    def _publish_bundle(self, bundle: Bundle) -> None:
        # Override in application to publish bundle to server
        pass


x3dh_configuration: Dict[str, Any] = {
    "identity_key_format": IdentityKeyFormat.CURVE_25519,
    "hash_function": HashFunction.SHA_256,
    "info": b"EPIC X3DH",
}


async def test_x3dh():
    # Create Alice and Bob's X3DH states
    alice_state = X3DHState.create(**x3dh_configuration)
    bob_state = X3DHState.create(**x3dh_configuration)

    # Bob publishes his bundle
    bob_bundle = bob_state.bundle

    # Alice initiates key agreement using Bob's bundle
    shared_secret_alice, associated_data, header = (
        await alice_state.get_shared_secret_active(bob_bundle)
    )

    # Bob completes key agreement using Alice's header
    shared_secret_bob, _, _ = await bob_state.get_shared_secret_passive(header)

    assert shared_secret_alice == shared_secret_bob
    print("X3DH key agreement successful!")
    print(f"Shared secret: {shared_secret_alice.hex()}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_x3dh())
