# Security Assessment — EPIC-1bit2qbit

_Initial review: 2026-06-02 · Updated: 2026-06-03 (re-verified against the wired client) · Reviewer: Claude (full-codebase review)_

**Threat model assessed:** malicious actors with full knowledge of the codebase,
and the system's posture against a **malicious / compromised server** (including
the TLS-terminating university gateway).

## Scope note

The C++ client is now **fully wired** end-to-end. `Client::do_login` unlocks the
DEK with a separate PIN, restores persisted state from `MessageStore`, brings up
the network stack, and authenticates; `do_send`, `handle_ws_frame`,
`on_deliver_message`, `on_key_bundle_response`, and the X3DH/ratchet session
helpers are all implemented. The original High findings (H1–H3) described an
earlier, partially-wired state and have since been resolved — they are retained
below with their resolution noted. The server `/ws` path is fully implemented.

---

## Resolved since initial review

### H1. Login password reused as the local key-encryption passphrase — RESOLVED

The original review found `do_login` passing the **same** secret to both
`unlock_dek` and the server login frame, leaking the at-rest KEK passphrase to the
server. The current code uses **two independent secrets**:

- `client/src/client/Client.cpp:230` — `crypto_->unlock_dek(key_pin, username, encrypted_dek_)`
  (a local PIN, never sent to the server).
- `client/src/client/Client.cpp:303` — `send_login_frame(username, auth_password)`
  (the server password).

The UI collects both (`do_login(username, auth_password, key_pin)`), so a
malicious or compromised server no longer learns the secret that protects local
private keys. The crypto design doc's domain-separation requirement is satisfied.

### H2. TOFU identity-key pinning not implemented — RESOLVED

The pin store is now backed by a real `pinned_keys` table:

- `client/src/messaging/MessageStore.cpp:194-209` — `pin_identity_key` /
  `load_pinned_identity_key` write and read SQLite rows.

The client pins on first contact and **compares on every inbound first message**,
dropping the message with a loud warning on mismatch
(`client/src/client/Client.cpp:503-507`). Remaining gap: there is still **no
out-of-band verification feature** (safety numbers / fingerprint comparison), so a
key change is detected but the original first-contact TOFU assumption is
unverifiable out of band. Tracked as a low-priority enhancement below (L7).

### H3. Server cert pinning unwired — RESOLVED

Cert pinning is wired and **now persisted across restarts**:
`do_login` loads the per-host pin from `MessageStore` before the first
`connect(server_cert_pin_)` and writes back the observed fingerprint on first
capture (`client/src/client/Client.cpp:299-310`,
`client/src/messaging/MessageStore.cpp:save_server_cert/load_server_cert`, keyed
`cert:<host>`). A cert swap between launches now trips the pin-mismatch check in
`TlsContext::verify_and_pin` instead of silently re-pinning. CA-chain + hostname
verification and TLS 1.3 pinning remain in place (`TlsContext.cpp:11-12`). The pin
is cleared on logout so a different account re-pins from its own store.

### M1. Double Ratchet state at rest — RESOLVED at the storage layer

Ratchet state still crosses the IPC boundary as raw `dr.json`
(`client/subprocess_handler.py:269, 285, 295, 306`), but the C++ side now wraps it
under the DEK via `storage_encrypt` before persisting
(`client/src/client/Client.cpp:600, 655` → `save_ratchet_state`). Message keys are
therefore **not** in cleartext at rest, so the forward-secrecy-on-stolen-device
concern is closed. The minor inconsistency that ratchet state crosses IPC
unwrapped while X3DH state is wrapped remains as a defense-in-depth note, not an
at-rest exposure.

---

## Open — Medium

### M2. No rate limiting → online brute force, registration spam, OTPK depletion

No throttling on any endpoint:

- **Login** (`server/backend/routes/ws.py:35`) — online password guessing; Argon2
  cost slows it but nothing blocks it.
- **`/register`** (`server/backend/routes/auth.py:14`) — unlimited account
  creation / DB fill.
- **`request_key_bundle`** (`server/backend/handlers/key_bundle.py:69-79`) — each
  request **pops one OTPK**. An attacker can repeatedly request a victim's bundle
  to drain the entire OTPK pool, forcing subsequent sessions onto the no-OTPK X3DH
  fallback (weaker forward secrecy for initial messages). Classic X3DH
  availability attack, currently free.

**Fix:** Per-account/per-IP rate limits on all three; cap OTPK consumption per
requester per window.

### M3. One-time prekeys are never pruned and can outlive their identity key

`handle_publish_key_bundle` (`server/backend/handlers/key_bundle.py:19-49`)
overwrites the bundle row on republish but **only ever `db.add()`s OTPKs** — never
deletes old ones:

1. A client republishing repeatedly bloats `one_time_pre_keys` unboundedly
   (storage DoS; bounded only by the 4096-byte frame cap per call).
2. After an identity-key rotation, stale OTPKs from the *previous* identity remain
   servable, so a requester can receive an OTPK that doesn't match the current
   identity key.

**Fix:** Delete existing OTPKs for the owner when the identity key changes; cap
pool size and reject/replace beyond it.

---

## Low / Informational

- **L1. Blockchain integrity depends entirely on the server's owner key.**
  `recordBatch` deliberately does not verify root↔leaves
  (`blockchain/contracts/MessageIntegrity.sol:100-107`); trust is the `onlyOwner`
  guard backed by `PRIVATE_KEY` in `server/.env`. A compromised server can refuse
  to anchor, anchor selectively, or omit messages. The chain only proves *"the
  server committed to this exact `mid:ciphertext` at time T."* Clients don't
  independently verify anchoring. Tamper-*evidence* for committed messages, not
  tamper-*prevention* against the server.
- **L2. Metadata at rest and in logs.** The anchored leaf preimage is
  `f"{mid}:{ciphertext}"` (`server/backend/daemons/batcher.py:27`), and
  `mid = sender:recipient:timestamp`. Combined with `DEBUG`-level logging of
  usernames/mids (`server/config.toml`, 7-day retention), substantial metadata is
  exposed server-side. Acknowledged in the threat model; consider raising the
  deployed log level and not logging mids.
- **L3. Username homograph/case.** `^[a-zA-Z0-9_.-]+$` treats `Alice`/`alice` as
  distinct (`server/backend/schemas/http.py:7`); enables display-spoofing of
  contacts. Consider casefold-normalization or a uniqueness collation.
- **L4. Merkle odd-node duplication** (`server/backend/blockchain/batcher.py:41`,
  `server/web-app/src/verifier.ts:31`) is Bitcoin-style, not OpenZeppelin-standard.
  Not exploitable here because the verifier rebuilds the full tree from *all*
  on-chain leaf events and checks against the stored root (never trusts an
  externally-supplied proof), and `onlyOwner` gates writes. Noting for the design
  doc's "OpenZeppelin-compatible" claim, which isn't quite accurate.
- **L5. Subprocess error strings surfaced to UI**
  (`client/subprocess_handler.py:332` → `client/src/crypto/CryptoProxy.cpp:107`) —
  minor info leak; keep crypto exception text generic.
- **L6. Batcher cutoff mixes aware/naive datetimes**
  (`server/backend/daemons/batcher.py:15` vs the aware `now` in
  `server/backend/handlers/messaging.py:72`). Correctness, not security, but it can
  shift the edit-window/anchoring boundary.
- **L7. No out-of-band identity verification.** Pinning detects key *changes* but
  there is no safety-number / fingerprint display to verify a contact's identity on
  first contact. Residual from H2.
- **L8. TLS terminates at a third-party gateway.** `server/nginx.conf:11-13`
  terminates TLS at the university gateway; gateway→VM traffic is plaintext HTTP.
  H1's fix removes the password-at-the-gateway exposure, and the server cert pin is
  now persisted across restarts (resolved with H3), so a gateway cert swap trips the
  pin check. Residual exposure: the gateway still sees plaintext on the VM hop, so a
  compromised gateway can read/alter the transport — defended against at the
  application layer by E2EE and identity-key pinning, not by TLS.

---

## What's solid

- Two-secret login: a local PIN unlocks the DEK, a separate password authenticates
  to the server, with a 3-strike PIN lockout
  (`client/src/client/Client.cpp:230, 303`).
- TOFU identity-key pinning with compare-on-fetch and drop-on-mismatch
  (`client/src/client/Client.cpp:503-507`,
  `client/src/messaging/MessageStore.cpp:194-209`).
- At-rest encryption of message bodies, ratchet state, and associated data under
  the DEK before persistence (`storage_encrypt`, `Client.cpp:600, 655`).
- Argon2id password hashing with a dummy-hash timing equalizer + always-hash on
  register — good username-enumeration and timing defense
  (`server/backend/auth/credentials.py:7`, `server/backend/routes/auth.py:15`).
- AEAD with associated data binding the ratchet header — prevents header
  substitution (`client/crypto_functions/ratchet.py:37-45`).
- All DB access via SQLAlchemy ORM with bound params — no SQL injection surface.
- WebSocket hardening: 16 MiB frame cap, server-mask rejection, control-frame
  validation, frame-size + 5-strike limits server-side
  (`client/src/connection/Connection.cpp:308-317`, `server/backend/routes/ws.py:75-98`).
- TLS 1.3-only, SNI + hostname verification, full error-queue drain
  (`client/src/connection/TlsContext.cpp`, `client/src/connection/Connection.cpp:130-157`),
  with TOFU server-cert pinning persisted per-host across restarts
  (`client/src/client/Client.cpp:299-310`).
- Routing-layer sender identity is set from the authenticated session, not client
  input (`server/backend/handlers/messaging.py:74`) — no sender spoofing at
  delivery; duplicate-session rejection prevents takeover
  (`server/backend/routes/ws.py:62`).
- DEK/X3DH-state wrapping binds username as AAD
  (`client/crypto_functions/dek.py:59`) — blobs can't be transplanted between
  accounts.

---

## Priority order

1. **M2 / M3** — server-side rate limiting and OTPK pruning; independently
   shippable, now the highest-impact open items.
2. **L7** — add a fingerprint / safety-number display for out-of-band identity
   verification.
