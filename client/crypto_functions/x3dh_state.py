"""Concrete X3DH State subclass.

python-x3dh (>= 1.0) ships ``State`` as an abstract base class: the application
must subclass it and implement ``_encode_public_key`` and ``_publish_bundle``
before ``State.create`` / ``State.from_json`` can be instantiated. This module
supplies that subclass so the rest of the crypto layer can use it.
"""

import x3dh


class X3DHState(x3dh.State):
    @staticmethod
    def _encode_public_key(key_format: x3dh.IdentityKeyFormat, pub: bytes) -> bytes:
        # The library only requires distinct public keys to map to distinct
        # encodings; the raw public-key bytes already satisfy that, so pass through.
        return pub

    def _publish_bundle(self, bundle: x3dh.Bundle) -> None:
        # Bundle publication is performed by the C++ client over WebSocket, not by
        # this subprocess. The library calls this during create(); nothing to do.
        pass
