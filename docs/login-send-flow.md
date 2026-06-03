# Login & Send-Message Flows

Function-call-level sequence diagrams for the two core client flows: a user
logging in, and a user sending a message.

> **Band colours:** teal tint = crypto / key op · blue tint = transport
> (TCP / TLS / WebSocket) · amber tint = authentication. Tints are translucent so
> they stay readable in both light and dark themes.
>
> **Status tags:** `✓` = code exists *and* is invoked on this path.
>
> **Implementation status:**
>
> **Client:** `CryptoProxy` (IPC bridge) and the `Client` orchestrator are
> implemented, and the full login + send paths are wired. Login takes two
> independent secrets — a **PIN** that unlocks the local DEK (`unlock_dek`) and a
> **server password** sent in the first WS frame — so the server never sees the
> at-rest key. `Client::do_login` unlocks the DEK, restores persisted X3DH state,
> ratchet state, pinned identity keys and conversation history from `MessageStore`
> (SQLite), brings up the `Connection` / `TlsContext` stack with TOFU cert
> capture, sends the login frame, and republishes the key bundle. `do_send`,
> `handle_ws_frame`, `on_deliver_message`, `on_key_bundle_response`,
> `encrypt_and_send` and `start_session_and_send` are all implemented. The
> encrypted DEK and X3DH state persist across runs via `MessageStore`'s key store
> (`save_dek`/`load_dek`, `save_encrypted_state`/`load_encrypted_state`). The
> server TLS pin is captured on first connect and persisted per-host in
> `MessageStore` (`save_server_cert`/`load_server_cert`), so it survives restarts
> and a cert swap between launches trips the pin check.
>
> **Server:** `/ws` is **fully implemented** (`server/backend/routes/ws.py` +
> `server/backend/handlers/`). It authenticates the first frame, registers the
> session in the `SessionRegistry` (rejecting a duplicate connection with `4002`),
> drains the offline queue, then runs a dispatch loop over `send_message` /
> `publish_key_bundle` / `request_key_bundle` frames (size-capped at 4096 bytes,
> with a 5-strike invalid-frame limit). `handle_send_message` routes to the online
> recipient via the registry or persists to the `TTLDeliveryQueue` (30-day) when
> offline, and records every message in `BlockchainMessageQueue` for later Merkle
> batching. The key-bundle directory (`handle_publish_key_bundle` /
> `handle_request_key_bundle`) stores bundles and consumes one-time pre-keys. The
> periodic Merkle batch to Sepolia (`server/blockchain/batcher.py`) is not yet
> wired as a running daemon.

---

## 1. User logs in

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant CX as Client orchestrator ✓<br/>(Client.cpp)
    participant CN as Connection ✓
    participant TL as TlsContext ✓
    participant PY as Crypto subprocess ✓<br/>(via CryptoProxy)
    participant SV as Server /ws ✓
    participant CR as auth: credentials ✓
    participant DB as MySQL

    U->>CX: enter username + PIN + password
    Note over CX,PY: CryptoProxy::start() ✓ — fork + 2 pipes, dup2 stdin/stdout,<br/>execlp python3 subprocess_handler.py (SIGPIPE ignored)

    rect rgba(0,150,136,0.12)
    Note over CX,PY: Unlock local key store (DEK) — Client::do_login ✓
    CX->>CX: MessageStore::load_dek(username) → encrypted_dek_ (persisted blob)
    CX->>PY: unlock_dek(PIN, username, encrypted_dek_) → call() → send_recv/read_line
    PY->>PY: _derive_kek (Argon2id) → AESGCM.decrypt → cache _active_dek
    PY-->>CX: {} ok  (wrong PIN → InvalidTag → error → 3-strike lockout)
    Note over CX: PIN unlocks the DEK locally; the server never sees it.<br/>load_encrypted_state + restore ratchet/pins/history from MessageStore
    end

    rect rgba(33,150,243,0.12)
    Note over CX,TL: TCP + TLS — Connection::connect(server_cert_pin_) ✓
    CX->>CN: connect(server_cert_pin_)
    CN->>CN: disconnect() teardown, then tcp_connect() resolve + connect
    CN->>SV: SSL_connect() — TLS 1.3, SNI + SSL_set1_host + verify PEER
    SV-->>CN: certificate chain
    CN->>TL: verify_and_pin() — X509_V_OK + SHA-256 fp vs pin (loaded from MessageStore)
    TL-->>CN: server_cert_fp_ (persisted per-host on first capture, reused on later runs)
    end

    rect rgba(33,150,243,0.12)
    Note over CN,SV: WebSocket upgrade — ws_handshake() ✓
    CN->>SV: GET Upgrade + Sec-WebSocket-Key (ws_key_base64)
    SV-->>CN: 101 Switching Protocols + Sec-WebSocket-Accept
    CN->>CN: check 101 + ws_compute_accept, start read_loop thread
    end

    rect rgba(255,160,0,0.14)
    Note over CX,DB: first WS frame is the login (no tokens) ✓
    CX->>CN: send_login_frame { username, password }
    CN->>SV: masked text frame over TLS
    SV->>SV: _authenticate() → LoginFrame.model_validate_json
    SV->>CR: verify_credentials() via asyncio.to_thread
    CR->>DB: query User by username
    CR->>CR: verify_password (Argon2id, RFC 9106) + needs_rehash check
    CR-->>SV: ok?
    alt malformed login frame
        SV-->>CN: close(4000 invalid login frame)
    else bad credentials
        SV-->>CN: close(4001 auth failed) → read_loop → on_disconnect_cb_
    else valid
        SV->>SV: SessionRegistry.register(username) — close(4002) if already connected
        SV->>SV: drain_offline_queue() → emit deliver_message for each queued frame
        SV->>SV: log "session opened", enter dispatch loop (session live)
    end
    end
```

---

## 2. User sends a message

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant CX as Client orchestrator ✓<br/>(do_send)
    participant CN as Connection ✓
    participant PY as Crypto subprocess ✓<br/>(via CryptoProxy)
    participant SV as Server /ws ✓

    Note over CX,SV: client + server both wired — do_send / handle_ws_frame drive the<br/>CryptoProxy methods below; the server handles every frame this flow emits<br/>(send_message / request_key_bundle)

    U->>CX: type message, press Enter

    alt First message to contact — X3DH initiation
        rect rgba(0,150,136,0.12)
        Note over CX,SV: queue plaintext in pending_sends_, fetch recipient key bundle ✓
        CX->>SV: request_key_bundle { target_username }
        SV->>SV: handle_request_key_bundle — load KeyBundle, consume one OTPK (SELECT … FOR UPDATE)
        SV-->>CX: key_bundle_response { identity_key, signed_pre_key + sig, one_time_pre_key | null }
        end

        rect rgba(0,150,136,0.12)
        Note over CX,PY: on_key_bundle_response → start_session_and_send — derive secret + encrypt
        CX->>PY: get_shared_secret_active(encrypted_state, bob_bundle)
        PY->>PY: _unwrap_state (DEK) → state.get_shared_secret_active()
        PY-->>CX: { shared_secret, ad, header, ratchet_pub, encrypted_state }
        CX->>PY: encrypt_initial_message(shared_secret, ratchet_pub, msg, ad)
        PY->>PY: DoubleRatchet.encrypt_initial_message()
        PY-->>CX: { encrypted_message, ratchet_state }
        end
        Note over CX: envelope = X3DH header + encrypted_message; pin peer IK +<br/>persist ratchet_state / encrypted_state via MessageStore ✓
    else Subsequent message — ratchet established
        rect rgba(0,150,136,0.12)
        CX->>PY: encrypt_message(ratchet_state, msg, ad)
        PY->>PY: DoubleRatchet.from_json().encrypt_message()
        PY-->>CX: { encrypted_message, ratchet_state (advanced) }
        end
    end

    rect rgba(33,150,243,0.12)
    Note over CX,SV: send_message frame over the live WS ✓ — client sends, server routes
    CX->>CN: send_text(send_message { recipient, ciphertext, mid })
    CN->>SV: ws_encode_frame (FIN + mask) → ssl_write_all
    SV->>SV: receive_text → size check (≤4096) → validate InboundFrame → _dispatch
    SV->>SV: handle_send_message — look up recipient User (unknown → ErrorFrame)
    SV->>SV: record in BlockchainMessageQueue (edit_window deadline → later Merkle-batch to Sepolia)
    alt recipient online (SessionRegistry.get)
        SV->>SV: deliver_message { sender, ciphertext, mid } → recipient WS
    else recipient offline
        SV->>SV: persist to TTLDeliveryQueue (30-day TTL), delivered on next login drain
    end
    end

    Note over CN,CX: Inbound ✓: read_loop → ws_decode_frame → on_message_cb_ →<br/>handle_ws_frame → on_deliver_message → CryptoProxy decrypt_initial_message /<br/>decrypt_message. Server emits deliver_message on direct delivery & offline-queue drain.
```
