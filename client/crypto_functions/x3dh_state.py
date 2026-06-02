"""Concrete X3DH State subclass.

python-x3dh (>= 1.0) ships ``State`` as an abstract base class: the application
must subclass it and implement ``_encode_public_key`` and ``_publish_bundle``
before ``State.create`` / ``State.from_json`` can be instantiated. This module
supplies that subclass so the rest of the crypto layer can use it.
"""

import x3dh


class X3DHState(x3dh.State):
    # Set by _publish_bundle when the library marks the published bundle stale
    # (a one-time pre key was consumed during a passive agreement, the signed pre
    # key rotated, or the state format migrated). Instance attribute, so it never
    # survives serialization — it only signals a change within a single IPC call.
    _bundle_dirty = False

    @staticmethod
    def _encode_public_key(key_format: x3dh.IdentityKeyFormat, pub: bytes) -> bytes:
        # The library only requires distinct public keys to map to distinct
        # encodings; the raw public-key bytes already satisfy that, so pass through.
        return pub

    def _publish_bundle(self, bundle: x3dh.Bundle) -> None:
        # The subprocess never touches the network — the C++ client publishes the
        # bundle over WebSocket. We can't push from here, so we only record that the
        # bundle changed; the handler surfaces it to C++ in its response.
        self._bundle_dirty = True

    def pop_published_bundle(self) -> x3dh.Bundle | None:
        """Return the bundle if it was re-published since the last check, else None.

        Lets a handler hand C++ a fresh bundle to re-publish whenever the library
        rotated keys as a side effect (notably consuming an OTPK in a passive X3DH).
        """
        if self._bundle_dirty:
            self._bundle_dirty = False
            return self.bundle
        return None
