# Server Flows

> **Color key:** dark grey = start/end · blue = process · amber = decision · green = success · red = error · purple = storage · teal = key/security op

---

## 1. Register

```mermaid
flowchart TD
    classDef terminal  fill:#37474F,stroke:#263238,color:#fff
    classDef process   fill:#1565C0,stroke:#0D47A1,color:#fff
    classDef store     fill:#6A1B9A,stroke:#4A148C,color:#fff
    classDef ok        fill:#2E7D32,stroke:#1B5E20,color:#fff

    A([POST /register]):::terminal --> B["Validate request & generate token"]:::process
    B --> C["Store user account + preloaded key bundle"]:::store
    C --> D([Return token]):::ok
```

---

## 2. Login

```mermaid
flowchart TD
    classDef terminal  fill:#37474F,stroke:#263238,color:#fff
    classDef process   fill:#1565C0,stroke:#0D47A1,color:#fff
    classDef decision  fill:#F57F17,stroke:#E65100,color:#000
    classDef error     fill:#B71C1C,stroke:#7F0000,color:#fff
    classDef ok        fill:#2E7D32,stroke:#1B5E20,color:#fff
    classDef store     fill:#6A1B9A,stroke:#4A148C,color:#fff

    A([POST /login]):::terminal --> B["Verify credentials"]:::process
    B -- invalid --> C([Return 401]):::error
    B -- valid --> D{"2FA required?"}:::decision
    D -- yes --> E["Return 302 — redirect to verification webapp"]:::error
    D -- no --> F["Create session / set online"]:::process
    F --> G["Drain offline message queue (up to TTL)"]:::store
    G --> H([Return session token]):::ok
```

---

## 3. WS — Send Message

```mermaid
flowchart TD
    classDef terminal  fill:#37474F,stroke:#263238,color:#fff
    classDef process   fill:#1565C0,stroke:#0D47A1,color:#fff
    classDef decision  fill:#F57F17,stroke:#E65100,color:#000
    classDef ok        fill:#2E7D32,stroke:#1B5E20,color:#fff
    classDef store     fill:#6A1B9A,stroke:#4A148C,color:#fff
    classDef keyop     fill:#00695C,stroke:#004D40,color:#fff

    A([WS: send message]):::terminal --> B["Enqueue in Message Queue"]:::process
    B --> C{"Receiver online?"}:::decision
    C -- yes --> D["Push to receiver's WS connection"]:::process
    C -- no --> E["Store in offline TTL queue"]:::store
    D --> F{"Key bundle cached?"}:::decision
    E --> F
    F -- yes --> G([Deliver complete]):::ok
    F -- no --> H["Fetch bundle from Key Bundle Directory\nTTL + SIG + PREKEY"]:::keyop
    H --> I([Return bundle to sender]):::ok
```

---

## 4. WS — Key Bundle Operations

```mermaid
flowchart LR
    classDef terminal  fill:#37474F,stroke:#263238,color:#fff
    classDef process   fill:#1565C0,stroke:#0D47A1,color:#fff
    classDef decision  fill:#F57F17,stroke:#E65100,color:#000
    classDef error     fill:#B71C1C,stroke:#7F0000,color:#fff
    classDef ok        fill:#2E7D32,stroke:#1B5E20,color:#fff
    classDef store     fill:#6A1B9A,stroke:#4A148C,color:#fff
    classDef keyop     fill:#00695C,stroke:#004D40,color:#fff

    subgraph REQ["Request Key Bundle"]
        R1([WS: request bundle]):::terminal --> R2["Look up Key Bundle Directory"]:::keyop
        R2 --> R3{"Found?"}:::decision
        R3 -- yes --> R4([Return bundle]):::ok
        R3 -- no --> R5([Return error]):::error
    end

    subgraph PUB["Publish Own Key Bundle"]
        P1([WS: publish bundle]):::terminal --> P2["Validate bundle\nsignature · TTL · format"]:::keyop
        P2 -- invalid --> P3([Return validation error]):::error
        P2 -- valid --> P4["Store in Key Bundle Directory"]:::store
        P4 --> P5([Return ACK]):::ok
    end
```

---

## 5. WS — Timeline Tick (Server-side Push)

```mermaid
flowchart TD
    classDef terminal  fill:#37474F,stroke:#263238,color:#fff
    classDef process   fill:#1565C0,stroke:#0D47A1,color:#fff
    classDef decision  fill:#F57F17,stroke:#E65100,color:#000
    classDef ok        fill:#2E7D32,stroke:#1B5E20,color:#fff
    classDef store     fill:#6A1B9A,stroke:#4A148C,color:#fff

    A([Server tick]):::terminal --> B["Find users who just came online"]:::process
    B --> C["Query pending messages from TTL queue"]:::store
    C --> D{"Messages found?"}:::decision
    D -- yes --> E["Push over active WS connection"]:::process
    E --> F["Remove delivered messages from queue"]:::store
    F --> G([Done]):::ok
    D -- no --> H([No-op]):::terminal
```
