# System Architecture

## System Overview

```mermaid
flowchart LR
    classDef entry      fill:#1565C0,stroke:#0D47A1,color:#fff
    classDef orch       fill:#E65100,stroke:#BF360C,color:#fff
    classDef transport  fill:#00695C,stroke:#004D40,color:#fff
    classDef messaging  fill:#00838F,stroke:#006064,color:#fff
    classDef security   fill:#B71C1C,stroke:#7F0000,color:#fff
    classDef blockchain fill:#4E342E,stroke:#3E2723,color:#fff
    classDef infra      fill:#546E7A,stroke:#37474F,color:#fff
    classDef storage    fill:#6A1B9A,stroke:#4A148C,color:#fff

    subgraph CA["Client Application"]
        UI["UI / CLI Layer (FTXUI)"]:::entry
        MLM["Message Lifecycle Manager"]:::messaging
        CONN["Connection Layer (Raw OpenSSL · Boost.Asio)"]:::transport
        ORCH["Main Orchestrator"]:::orch
        CRYPTO["Python Crypto Subprocess\n(Unix socket · JSON IPC)"]:::security
        KEYS["Local Key Manager"]:::security
        DBC[("Encrypted DB")]:::storage
    end

    subgraph ISE["ISE Server"]
        API["API — Register"]:::entry
        WS["WebSockets Router / Dispatcher"]:::transport
        SESSION["Session Manager"]:::messaging
        MQ["Message Queue"]:::messaging
        KBD["Key Bundle Directory Service"]:::security
        AUTHN["Authentication Handler"]:::security
        BC["Blockchain Batching Service"]:::blockchain
        LOG["Logging / Rate Limiting"]:::infra
        WEBAPP["Verification Webapp"]:::entry
        DBS[("DB (SQL)")]:::storage
    end

    CONN -->|HTTPS| API
    CONN -->|WSS| WS

    style CA fill:#E3F2FD,stroke:#1565C0
    style ISE fill:#E8F5E9,stroke:#1B5E20
```

---

## Client Application — Internals

```mermaid
flowchart TB
    classDef entry      fill:#1565C0,stroke:#0D47A1,color:#fff
    classDef orch       fill:#E65100,stroke:#BF360C,color:#fff
    classDef transport  fill:#00695C,stroke:#004D40,color:#fff
    classDef messaging  fill:#00838F,stroke:#006064,color:#fff
    classDef security   fill:#B71C1C,stroke:#7F0000,color:#fff
    classDef storage    fill:#6A1B9A,stroke:#4A148C,color:#fff

    subgraph CPP["C++ Binary"]
        UI["UI / CLI Layer (FTXUI)"]:::entry
        MLM["Message Lifecycle Manager"]:::messaging
        CONN["Connection Layer\n(Raw OpenSSL · Boost.Asio)"]:::transport
        ORCH["Main Orchestrator"]:::orch
        KEYS["Local Key Manager"]:::security
        DBC[("Encrypted DB (SQL)\n· Local key storage\n· Message / data history")]:::storage
    end

    subgraph PY["Python Crypto Subprocess"]
        CRYPTO["Cryptography Module\n(Double Ratchet · PQXDH · AES-256-GCM)"]:::security
    end

    ORCH --> UI
    ORCH --> MLM
    ORCH --> CONN
    ORCH -.->|"Unix socket · JSON IPC"| CRYPTO
    ORCH --> KEYS
    KEYS --> DBC
    MLM --> DBC

    style CPP fill:#E3F2FD,stroke:#1565C0
    style PY  fill:#FCE4EC,stroke:#B71C1C
```

---

## ISE Server — Internals

```mermaid
flowchart TB
    classDef entry      fill:#1565C0,stroke:#0D47A1,color:#fff
    classDef transport  fill:#00695C,stroke:#004D40,color:#fff
    classDef messaging  fill:#00838F,stroke:#006064,color:#fff
    classDef security   fill:#B71C1C,stroke:#7F0000,color:#fff
    classDef blockchain fill:#4E342E,stroke:#3E2723,color:#fff
    classDef infra      fill:#546E7A,stroke:#37474F,color:#fff
    classDef storage    fill:#6A1B9A,stroke:#4A148C,color:#fff

    API["API — Register"]:::entry
    WS["WebSockets Router / Dispatcher"]:::transport
    AUTHN["Authentication Handler"]:::security
    SESSION["Session Manager"]:::messaging
    MQ["Message Queue"]:::messaging
    KBD["Key Bundle Directory Service"]:::security
    BC["Blockchain Batching Service"]:::blockchain
    LOG["Logging / Rate Limiting"]:::infra
    WEBAPP["Verification Webapp"]:::entry
    DBS[("DB (SQL)\n· User account details\n· Offline messages (up to TTL)")]:::storage

    API --> AUTHN
    API --> LOG
    WS --> AUTHN
    WS --> LOG
    AUTHN --> SESSION
    WS --> SESSION
    WS --> MQ
    MQ --> KBD
    MQ --> DBS
    SESSION --> DBS
    KBD --> DBS
    BC --> DBS
```

---

## Component Legend

| Color | Layer | Components |
|-------|-------|-----------|
| Blue | Interface / Entry | UI/CLI Layer, API, Verification Webapp |
| Orange | Orchestration | Main Orchestrator |
| Teal | Transport | Connection Layer, WebSockets Router |
| Cyan | Messaging & State | Message Lifecycle Manager, Session Manager, Message Queue |
| Red | Security & Keys | Python Crypto Subprocess (separate process, Unix socket IPC), Local Key Manager, Auth Handler, Key Bundle Directory |
| Brown | Blockchain | Blockchain Batching Service |
| Grey | Infrastructure | Logging / Rate Limiting |
| Purple | Storage | Encrypted DB, DB (SQL) |
