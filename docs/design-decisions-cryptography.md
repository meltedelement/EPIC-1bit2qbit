# Cryptographic Design Decisions

This document will be the basis for creation of our Cryptographic Design Document required by the project spec. It covers primitive selection, parameter justification, and the threat model.

---

## 1. Authenticated Encryption (AEAD)

### Chosen scheme: AES-256-GCM

**Standard reference:** NIST SP 800-38D

**Nonce (IV):** 96-bit, as strongly recommended by NIST SP 800-38D §8.2. The spec permits lengths from 1 to 2⁶⁴−1 bits, but 96-bit nonces allow the most efficient internal counter construction and are the only length for which the GCM security proof applies without caveats.

**Nonce strategy:**

- 96-bit pseudorandom nonce per key, permissable by NIST, and we are never hitting the 2^32 birthday bound limit.

**Key length — why 256-bit:**
AES-256 provides a 128-bit security level against quantum adversaries under Grover's algorithm (halves the brute-force cost), compared to AES-128's 64-bit post-quantum security. As this system may handle messages with long-term confidentiality requirements, 256-bit keys are appropriate.

**TODO:** Identify a citation for the quantum key-length argument (NIST IR 8105 or NIST SP 800-57 Part 1 Rev 5 §5.6.1 are candidates).

**Why AES-256-GCM and not ChaCha20-Poly1305:**
Both are standard AEADs. AES-256-GCM is chosen because AES-NI hardware acceleration is widely available on our target platforms (x86 and ARM64), making it the faster choice in practice. ChaCha20-Poly1305 would be the better choice on platforms without hardware AES; this is a known limitation.

**Forbidden constructions (will not use):**
Custom AEAD, Encrypt-and-MAC, MAC-then-Encrypt, ECB mode, non-AEAD schemes.

---

## 2. Key Establishment and Sender Authentication

### Chosen scheme: X3DH + Double Ratchet (Signal Protocol)

**References:**

- Signal X3DH specification: [https://signal.org/docs/specifications/x3dh/](https://signal.org/docs/specifications/x3dh/)
- Signal Double Ratchet specification: [https://signal.org/docs/specifications/doubleratchet/](https://signal.org/docs/specifications/doubleratchet/)

**Libraries:**

- [`python-x3dh`](https://github.com/Syndace/python-x3dh) — X3DH implementation used directly, part of the OMEMO reference implementation. Identity keys are Ed25519, hash function SHA-256, info string `b"EPIC"`, signed prekey rotation period 7 days, OPK refill threshold 99 / target 100.
- [`python-doubleratchet`](https://github.com/Syndace/python-doubleratchet) — Double Ratchet with X25519 DH ratchet, HKDF root chain KDF (SHA-256, info `b"EPIC Root Chain KDF"`), separate-HMAC message chain KDF, AES-256-GCM AEAD.

**Construction:**

- Initial key agreement uses **X3DH** (Extended Diffie-Hellman). The X3DH output feeds the Double Ratchet session.
- The DH ratchet step uses X25519 (Curve25519) for ephemeral key exchange.
- Each message is encrypted with AES-256-GCM; associated data binds the ciphertext to the Double Ratchet message header (ratchet public key, sending chain length, previous sending chain length), preventing header substitution attacks.

**Security properties:**

- **Perfect Forward Secrecy (PFS):** Compromise of long-term keys does not expose past session keys, because the Double Ratchet derives fresh ephemeral keys for each message chain.
- **Post-Compromise Security (PCS) / Break-in Recovery:** After a session key is compromised, the ratchet recovers security as soon as the next DH ratchet step occurs (requires a message round-trip).

**Sender authentication:**
Recipients can verify message origin because the X3DH handshake binds the sender's long-term identity key into the shared secret. A forged message from a different sender would not produce the correct shared secret and would fail AEAD authentication.

**Trust model:**
Trust-On-First-Use (TOFU) with key pinning. When Alice first communicates with Bob, she fetches Bob's identity key from the server and pins it locally. Subsequent sessions verify against the pinned key. If the key changes, Alice is warned.

A compromised server can substitute a malicious key for a new contact before the first message (MITM on first contact). This is a known limitation of TOFU — the server cannot forge messages to an existing pinned contact, but it can intercept a first contact before pinning occurs. This limitation is stated explicitly in §6 (Limitations).

**Key revocation:**
Not implemented in this version (out of scope). This is a known limitation.

---

## 3. Password Hashing (Server-Side)

### Chosen function: Argon2id

**Reference:** RFC 9106 — Argon2 Memory-Hard Function for Password Hashing and Proof-of-Work Applications (§4 recommends Argon2id for general password hashing).

**Why Argon2id over bcrypt/scrypt/PBKDF2:**
Argon2id is both memory-hard and time-hard (the "id" variant combines the side-channel resistance of Argon2i with the GPU resistance of Argon2d). PBKDF2-HMAC-SHA256 is not memory-hard and is therefore faster to attack with GPU clusters. bcrypt is limited to 72-byte passwords and has no GPU-resistance guarantees comparable to Argon2id.

**Parameters (TODO — finalise from OWASP recommendations):**
OWASP recommends for Argon2id (as of their current cheat sheet):

- **Minimum:** m=19456 (19 MiB), t=2, p=1
- **Preferred:** m=65536 (64 MiB), t=3, p=4

Parameters must be tuned to the server hardware during integration testing. The selected parameters must be recorded in the final design document alongside the measured hash time on the deployment hardware.

---

## 4. Key Derivation

### Chosen function: HKDF-SHA-256

**Reference:** RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function (HKDF).

HKDF is used to derive multiple keys from a shared secret (e.g. the X3DH output). Separate `info` strings achieve domain separation so that keys derived for different purposes (encryption key, MAC key, etc.) are cryptographically independent.


**NIST SP 800-132 guidance:**
Per NIST SP 800-132, the master key (MK) derived from the user's password is treated as a Key Encryption Key (KEK). A fresh random Data Protection Key (DPK) is generated to protect the actual data, and the MK wraps the DPK. This separates the password-derived key from the data encryption key, so that re-keying data does not require the user's password.

---

## 5. Key Storage at Rest (Local Private Keys)

### Scheme: Argon2id-derived key + AES-256-GCM wrapping

**Reference:** OWASP Key Management Cheat Sheet — [https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html)

When a user's long-term private key is stored on their device, it is encrypted using AES-256-GCM under a key derived from the user's passphrase via Argon2id.

**Why different Argon2id parameters from server-side password hashing?**
The server-side parameters are tuned so that the server can handle many concurrent login attempts without becoming a bottleneck. The at-rest key derivation runs only on the client device and only once per session unlock, so **higher parameters** are appropriate and desirable — it needs to be harder to brute-force from a stolen device than from a server database breach.

The two uses must be **domain-separated** (different salt namespaces or `context` strings) so that a database breach does not help an attacker crack a stolen device's key, or vice versa.

**TODO:** Define the specific Argon2id parameters for at-rest encryption and document them here.

---

## 6. Threat Model

### Attacker Classes


| Property                                             | Passive network attacker | Active network attacker | Honest-but-curious server             | Fully compromised server                           |
| ---------------------------------------------------- | ------------------------ | ----------------------- | ------------------------------------- | -------------------------------------------------- |
| Cannot read message plaintext                        | ✓ (TLS + E2EE)           | ✓ (TLS + E2EE)          | ✓ (E2EE; server never sees plaintext) | ✓ (AEAD; server has only ciphertext)               |
| Cannot forge messages                                | ✓                        | ✓                       | ✓                                     | ✓ (AEAD authentication + sender binding)           |
| Cannot tamper with ciphertext undetectably           | ✓                        | ✓                       | ✓                                     | ✓ (GCM authentication tag)                         |
| Cannot recover passwords from DB breach              | —                        | —                       | ✓ (Argon2id)                          | ✓ (Argon2id)                                       |
| Cannot recover local private keys from stolen device | —                        | —                       | —                                     | ✓ (at-rest AES-256-GCM under Argon2id-derived key) |
| Cannot MITM a first contact                          | ✓                        | ✓                       | ✓                                     | **✗ (TOFU limitation — see below)**                |
| Cannot MITM an established (pinned) contact          | ✓                        | ✓                       | ✓                                     | ✓ (key pinned after first contact)                 |


### Properties That Do NOT Survive Full Server Compromise

- **First-contact MITM:** A fully compromised server can substitute its own key before Alice pins Bob's key. After the first message is pinned, this attack is no longer possible. This is an inherent limitation of TOFU without a PKI.
- **Message delivery:** A compromised server can drop messages or refuse to deliver them. We provide no guarantee of delivery against a compromised server.
- **Metadata:** A compromised server knows who is communicating with whom (sender and receiver IDs are necessary for routing). Message contents are protected; communication metadata is not.

### Known Limitations

1. **No post-quantum security.** X3DH and the Double Ratchet both rely on X25519 (classical DH). A sufficiently powerful quantum computer could break the key agreement and ratchet steps. This is a known limitation of the classical Signal Protocol and is explicitly acknowledged — post-quantum key agreement (e.g. PQXDH with ML-KEM) was considered but not implemented.
2. **No key revocation:** If a long-term identity key is compromised, there is no mechanism to revoke it and notify contacts. Contacts will continue to use the compromised key until manually updated.
3. **TOFU first-contact vulnerability:** As described above.
4. **No forward secrecy against device compromise:** If an attacker compromises a device and extracts the at-rest private key (e.g. via the user's passphrase), they can decrypt all messages stored locally on that device. The Double Ratchet limits this to already-stored messages, not future ones.
5. **Metadata exposure to server:** The server necessarily knows sender, receiver, and timestamp for routing purposes.
6. **No anonymous messaging:** User identity is tied to an account registered with the server.

