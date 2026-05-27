# CS4436 Cybersecurity — Epic Project 2026

## Project Summary

Students are tasked with the design and implementation of a **secure messaging application** that guarantees confidentiality, integrity, and authenticity of communications. The application must incorporate concepts from all four subjects studied during the CS4455 block.

Students will build one or more desktop clients that connect to a common back-end server. At a minimum, a client must be created using C++ with appropriate libraries for cryptography and secure connectivity.

A second optional client can be created using HTML and JavaScript and should use the Web Crypto API and web security elements.

### Client Operations

Clients must support:

- User sign-up, login and password management
- Viewing a list of sent and received messages
- Creating and sending a new message
- Forwarding a message to another user after verifying their identity
- Revoking a user's access to a previously shared message
- Downloading a message (owned or shared)
- Deleting a message

### Server

Students will build a server application to handle authentication and to provide an API for the clients to interact with. The back-end can be developed in any language (NodeJS, Python, or other).

The messaging system must employ end-to-end encryption, secure network connectivity, and a C++ client component. A blockchain element will record message digests and timestamps to provide tamper-evident integrity verification.

Teams have flexibility in their messaging architecture (real-time, asynchronous, or hybrid) but must satisfy the requirements of each subject as described below.

### Overall Marking Scheme

The CS4436 block is divided into four equally weighted subjects. Each subject contributes 25% to the overall epic project grade, for a total of 100%. Within each subject, marks are distributed across the criteria defined in that subject's rubric.

---

## Marks Breakdown

| Minor | Weight |
|---|---|
| Computer Networks & Cybersecurity (Burkley) | 25% |
| C++ Programming (Memon) | 25% |
| Cryptography (O'Brien) | 25% |
| Blockchain (Le Gear) | 25% |
| **Total** | **100%** |

---

## Our Team

**Team 2 — 1bit2qbit**

| Name | Presentation |
|---|---|
| Skye Fitzpatrick | Thursday 4th June, 10:00 |
| James Hayes | Thursday 4th June, 10:00 |
| Aaron O'Doherty | Thursday 4th June, 10:00 |

---

## Project Server

A cloud server is available for teams to run cloud backends.

- **Domain:** `THEBURKENATOR.COM`
- **Our virtual host:** `1BIT2QBIT.THEBURKENATOR.COM`
- **VM access:** `ALDERAAN.SOFTWARE-ENGINEERING.IE`
- VMs are created with Ubuntu Linux by default; other distros can be used as needed.
- Teams may install their own development environments and back-ends on their respective VMs.

---

## Submission Requirements

Upload a zipped archive of your project's GitHub repository to Brightspace by **Wednesday 3rd June 2026 at 5:00 PM**.

### Archive must include

- All source code for the project
- A `README` file with clear instructions on how to install dependencies, set up the project, and run it

### Cover document (PDF or Markdown) alongside the archive, containing

- Group name and project URL
- Full name and student ID of each group member
- URL of the GitHub repository used for the project
- A breakdown of each member's contributions:
  - An estimated percentage of the overall work completed by each person
  - The specific features, components, or tasks each member worked on
- Any additional design summaries, diagrams, or explanations requested by the topic-specific requirements below

### AI Prompt Artefacts (New for 2026)

The submission **must include** a record of AI tool usage during development:

- Screenshots or exported logs of significant prompts and responses from AI coding assistants (e.g. GitHub Copilot, ChatGPT, Claude)
- A brief reflective commentary on how AI tools were used, what worked well, and what required manual correction
- Evidence of critical evaluation of AI-generated code (e.g. where you rejected, modified, or debugged AI output)

These artefacts will be discussed during the interview. Students must be able to explain their prompting strategies and critically evaluate the AI-generated code in their submission.

---

## Presentation and Interview

Teams will present and demonstrate their project, followed by a panel interview. Students will be expected to clearly explain, justify, and defend the design decisions made in their submission across all four subjects.

### Format

- Maximum **10 minutes** for team presentation and demonstration
- Maximum **20 minutes** for panel questioning (including AI prompt critique)
- Total: **30 minutes** per team (strictly enforced)

### AI Prompt Critique

During the interview, each student may be asked to:

- Walk through a specific AI interaction from their submitted artefacts
- Explain why they prompted in a particular way
- Identify strengths and weaknesses in the AI-generated output
- Describe what they changed and why

### Important

- Every student is expected to understand all the code in the project, even if they did not author it themselves
- Failure to adequately explain the solution, regardless of whether it is technically correct, will result in a loss of marks
- Marks are awarded on an **individual basis** (not every member of the team will necessarily receive the same grade)

---

## Subject Requirements

### Computer Networks & Cybersecurity (Mark Burkley) — 25%

- **Secure connectivity** (SSL/TLS between client and server)
  - Client verifies authenticity and validity of SSL certificate
- **Server-side security and authentication**
  - Users are securely authenticated and authorised
- **Vulnerability testing and penetration testing report**
- **Network architecture documentation**
  - Connections to external services (MySQL server, etc.) are documented
- Front end programs must create SSL protected connections to the virtual host
  - A back-end service running on the server should accept and process requests
  - Part of the back-end may be written in C++ with HTML parsing in NodeJS or Python, or the entire back-end can be written in one of those languages
- Teams should demonstrate ability to write code that resolves host names and establishes secure connections
  - Using low-level socket calls with `libcrypto` and `libssl` would be impressive; using `libcurl` is acceptable if time is tight
- The implemented solution must be tested and ensure protection against undesired side effects
- Students must demonstrate they have implemented controls and actively checked for:
  - Improper Input Validation
  - Broken Authentication
  - Broken Access Control
  - Cryptographic Issues
  - Injection
  - Security Misconfiguration
  - Sensitive Data Exposure
  - Vulnerable Components
- Both front end and backend services are expected to be resilient against common vulnerabilities and exploits
- Students are encouraged to include a **penetration testing report** detailing tests executed and their findings

---

### C++ Programming (Kashif Memon) — 25%

Students must create a C++ component for the secure messaging application. This could be a command-line client, a GUI/tooling component, a message-processing module, a local message store, or another C++ part that connects clearly to the EPIC project.

The C++ work does not need to implement the entire messaging system, but it must be a **meaningful part** of it and must be demonstrated during the final presentation/interview.

#### Requirements

1. **C++ Component** — Build a working C++ component related to the secure messaging app (e.g. sending/preparing messages, receiving/parsing/displaying messages, storing local message history, validating message data, providing a simple client interface)

2. **Code Structure**
   - Use more than one source file where appropriate
   - Use clear `.h`/`.hpp` and `.cpp` files
   - Use CMake if possible, or clearly document any alternative build method

3. **Functions and Classes**
   - Use functions to break the program into smaller tasks
   - Use classes to model important parts of the system (e.g. `User`, `Message`, `Conversation`, `Client`, `MessageStore`)
   - Use public and private access correctly
   - Use constructors where needed

4. **Object-Oriented Programming**
   - Use OOP where it helps the design
   - Use inheritance or polymorphism only where it makes sense
   - Students should be able to explain why they used their class structure

5. **Memory Management**
   - Avoid memory leaks and unsafe pointer use
   - Prefer normal objects, references, STL containers, and smart pointers
   - Use `std::unique_ptr` or `std::shared_ptr` only where appropriate
   - Students should be able to explain who owns important objects

6. **STL and Modern C++**
   - Use suitable STL containers: `std::vector`, `std::map`, `std::set`, `std::unordered_map`
   - Use STL algorithms where appropriate: `std::find`, `std::sort`, `std::count`, `std::copy`
   - Use lambdas where useful
   - Use `const` and references correctly

7. **Documentation and Interview**
   - Include README instructions for building and running the C++ component
   - Each student must be able to explain: what the component does, how the code is organised, how the classes work, how memory is managed, what STL containers/algorithms were used, and how AI tools were used (if applicable)

---

### Cryptography (Eoin O'Brien) — 25%

The messaging application must provide **end-to-end encrypted (E2EE)** communication between users. When Alice sends a message to Bob, only Bob can read it, and Bob can verify it genuinely came from Alice. The server relays ciphertext and stores metadata, but it cannot see message contents or undetectably tamper with them.

#### Threat Model

The design must guarantee confidentiality, integrity, and authenticity against:

- A **passive network attacker** who can read all traffic between clients and the server
- An **active network attacker** who can additionally modify, drop, replay, or inject traffic
- An **honest-but-curious server** that faithfully runs your protocol but logs everything it sees
- A **fully compromised server** controlled by the attacker, with full access to the database and able to send arbitrary responses to clients

A compromised server can drop messages, refuse to deliver them, or serve malicious public keys to new users. It **must not** be able to read message plaintexts, forge messages from one user to another, or tamper with ciphertexts without detection. The design document **must** state explicitly which properties survive server compromise and which do not.

Passwords must not be recoverable from a server database breach, and local private keys at rest must not be recoverable from a stolen unlocked laptop.

#### Requirements

1. **End-to-End Authenticated Encryption**
   - Encrypt all message payloads under a standardised AEAD scheme (e.g. AES-256-GCM, ChaCha20-Poly1305, or another standard AEAD with explicit justification)
   - The server must not be able to read plaintext or alter ciphertext undetectably, even if fully compromised — demonstrable at the demo
   - Custom AEAD constructions, Encrypt-and-MAC, MAC-then-Encrypt, and non-AEAD schemes are **not acceptable**

2. **Key Establishment and Sender Authentication**
   - Establish shared cryptographic state between users without revealing it to the server (e.g. HPKE Mode_Auth, RFC 9180, with DHKEM(X25519, HKDF-SHA256) and an approved AEAD)
   - Recipients must be able to verify message origin
   - The design document must state the trust model and justify it. TOFU (with pinning) is acceptable and expected for most teams; PKI requires full justification including key revocation

3. **Password and Key Derivation**
   - Server-side password verification must use an appropriate password hashing function, with choice and parameters justified
   - Use HKDF with explicit info and salt for any derivation of multiple keys from a shared secret
   - If a user's long-term private key is stored locally, encrypt it at rest under a key derived from a user secret, with KDF parameters separate from server-side password verification

4. **Implementation Standards**
   - Use only vetted cryptographic libraries: libsodium, cryptography, PyCryptodome, Web Crypto, OpenSSL EVP, hpke-js, or pyhpke
   - All randomness must come from an appropriate CSPRNG
   - **Forbidden:** hand-rolled primitives, MD5 or SHA-1 in security-relevant roles, DES, 3DES, RC4, ECB mode, Dual_EC_DRBG, textbook RSA, hardcoded keys, hardcoded IVs, nonce reuse

5. **Cryptographic Design Document** (approx. 2–6 pages, PDF or Markdown)
   - State the threat model across all four attacker classes; properties not held under server compromise must be named explicitly
   - Provide a construction walkthrough with diagrams covering registration, key publication, send, receive, and storage at rest
   - Justify every cryptographic primitive at parameter level with citations to RFCs or papers (section numbers where appropriate) — "it's standard" and "Eoin recommended it" are not justifications
   - State known limitations honestly

6. **Understanding and Explanation** — Students must be able to explain:
   - AEAD and why authenticated encryption is required
   - Nonce handling and the consequences of nonce reuse
   - The role of HKDF and domain separation
   - Memory-hard password hashing and parameter selection
   - The threat model the design defends against and the properties it does not provide
   - Any deviation from recommended primitives and/or parameters

---

### Blockchain (Andrew Le Gear) — 25%

Students must demonstrate the application of blockchain technology to provide tamper-evident integrity verification of messaging data.

#### Requirements

1. **Smart Contract Development**
   - Write a Solidity smart contract that stores message conversation digest hashes periodically (keccak256)
   - Deploy the contract to the **Ethereum Sepolia testnet**
   - The contract should accept a message conversation hash and record it alongside the block timestamp
   - Provide the deployed contract address and ABI in the submission

2. **Message Digest Recording**
   - When a message (or conversation segment) is sent, compute its keccak256 hash
   - Write the hash to the deployed smart contract via a transaction
   - Store the corresponding transaction hash for later verification
   - Consider trade-offs in persisting to the chain (a hash per message may be excessive)

3. **Verification Page**
   - Implement a web-based verification interface that allows a user to:
     - Input or paste original message content
     - Retrieve the on-chain hash and timestamp for a given transaction
     - Compare the computed hash of the provided content against the on-chain record
     - Display a clear pass/fail fidelity result with timestamp information
   - This page should be accessible independently of the messaging application

4. **Understanding and Explanation** — Students must be able to explain:
   - Hash functions and why keccak256 is used
   - How Ethereum transactions work
   - Gas costs
   - The immutability guarantees of blockchain
   - The difference between on-chain and off-chain data

---

## Assessment Rubrics

### Grading Scale

| Level | Percentage Band |
|---|---|
| Excellent | 80–100% |
| Very Good | 60–79% |
| Good | 50–59% |
| Acceptable | 40–49% |
| Poor | 0–39% |

### Computer Networks & Cybersecurity (Burkley) — 40 marks

| Criterion | Marks |
|---|---|
| Network coding using sockets API | 10 |
| Crypto coding using OpenSSL, WebCrypto, etc. / SSL certificate verification | 10 |
| Secure coding and input validation | 10 |
| Pentest and known vulnerabilities | 10 |

### C++ Programming (Memon) — 40 marks

| Criterion | Marks |
|---|---|
| C++ Component and Project Integration | 10 |
| Code Structure and Organisation | 10 |
| Functions, Classes, and OOP Design | 10 |
| Modern C++, Memory Safety, Documentation, and Interview Understanding | 10 |

### Cryptography (O'Brien) — 25%

| Criterion | Marks |
|---|---|
| Authenticated Encryption | 5% |
| Key Establishment & Sender Authentication | 5% |
| Password & Key Derivation | 5% |
| Design Document | 5% |
| Understanding & Defence | 5% |

### Blockchain (Le Gear) — 25%

| Criterion | Marks |
|---|---|
| Smart Contract | 5% |
| Message Digest Integration | 5% |
| Verification Page | 5% |
| Understanding | 5% |

---

## Academic Integrity

This is a group project. While collaboration within teams is expected and encouraged, all submitted work must be the team's own. Use of AI tools is permitted and encouraged as a development aid, but students must:

- Understand and be able to explain all code in their submission
- Submit AI prompt artefacts as described above
- Be prepared to critically evaluate AI-generated code during the interview

Plagiarism, contract cheating, or submission of work that a student cannot explain will be treated as an academic integrity violation under University of Limerick regulations.

While this is a group project, grades are awarded individually. Lecturers reserve the right to adjust individual grades up or down based on each student's contribution and their demonstrated understanding during the interview.
