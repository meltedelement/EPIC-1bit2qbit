# Design Decisions

Decisions and notes captured across team biweekly checkin sessions. Cryptographic design decisions are in a separate document: [design-decisions-cryptography.md](./design-decisions-cryptography.md).

---

## Process & Workflow

_Agreed at bi-weekly check-in, Tuesday 19th May 2026._

### Timeline

- **3 days** design
- **10 days** code
- **2 days** penetration testing
- **2 days** documentation
- Bi-weekly check-in meetings to track progress against the timeline

### Branch Naming

```
/<name>/<conventional-commit-type>/<short-description>
```

e.g. `skye/feat/websocket-handler`, `james/fix/argon2-params`

### PR Process

1. Create PR
2. Resolve Copilot suggestions in a loop until all clear
3. Upload AI interaction log as a file attachment in a GitHub comment at the bottom of the PR
4. Add a short note on what went well, what was rejected, modified, or corrected from AI responses
5. Request review from at least one other team member before merging to `main`

This approach keeps AI artefacts co-located with the code changes they relate to, making the final submission collation straightforward.

---

## System Architecture

### Messaging Model

We are using a **hybrid real-time and asynchronous** model.

**Real-time path (receiver online):** When a user connects to the server, a WebSocket connection is instantiated. Messages are pushed to the client over this socket immediately.

**Async path (receiver offline):** Messages are stored server-side until the receiver reconnects. Messages have a **TTL of 30 days** — if the receiver has been continuously offline for 30 days, the stored message is discarded.

A fully asynchronous poll-based model was rejected because it would require online clients to constantly poll for new messages, which is inefficient and increases latency.

### Message History Storage

Message history is **decentralised** — stored on user devices, not on the server. The server acts as a relay and temporary store only.

### Message Editing and Deletion

- A user can edit or delete their own messages **for both parties** within a fixed time window after sending (exact window TBD — every _x_ minutes after send).
- After this window closes, the server creates an **off-chain hash** of the confirmed message block, which is then committed to the **Sepolia blockchain** via the Smart Contract.
- After the window closes, a user may still delete a message **for themselves only** (local deletion), but cannot alter what the other party sees.

This design gives us an auditable, tamper-evident record on-chain for messages that have passed the edit window, while still offering a reasonable UX grace period.

---

## Requirements Specification

### Client / User Requirements

Users must be able to:

- Create an account
- Log in to an existing account
- Send a message
- Delete a message from both parties within the deletion timeframe
- Delete a message for themselves only after the deletion timeframe
- Edit a message for both parties within the editing timeframe
- Forward a message from one chat to another
- View sent chats per user
- Change their password
- Download an encrypted message object (for blockchain verification)
- Use the above object to verify a message was sent and retrieve its transaction ID
- Verify server certificate validity and authenticity
- Receive a warning on receipt of a tampered message
- Check the delivery and read status of a message they sent

### Server Requirements

The server must be able to:

- Listen for and accept connections from users
- Store messages up to the TTL while the receiver is offline
- Route messages to connected users
- Instantiate WebSocket connections when users connect
- Store messages until the end of the edit/deletion period, then hash the message blocks off-chain before committing to the blockchain
- Apply updates or deletions to stored messages when a valid request is received within the allowed timeframe
- Authenticate and authorise users
- Check for and protect against common network security threats

### Out of Scope

The following are explicitly out of scope for this project:

- Group chats
- Attachments (files, images, etc.)
- Online statuses / presence indicators
