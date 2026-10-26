# Security design

Academic assessment: the implemented controls and local regressions support academic demonstration and review. They are not an independent security audit. Installer drafts stay unpublished, unsigned previews; see [academic readiness](ACADEMIC-READINESS.md) and [packaging](PACKAGING.md).

## Scope

Serein Vault is a local desktop application with **one owner per encrypted file**. There is no server, email reset provider, administrator account, or shared-user role system. Usernames identify an owner of a selected vault, not a globally unique identity.

A closed vault protects against a reader without credentials. Possession of the recovery key grants recovery power equivalent to login. An unlocked process holds keys, SQLite pages and displayed plaintext in memory; Python cannot guarantee zeroization. Malware, administrative access, dumps, swap/hibernation, screen capture, and clipboard history remain outside this boundary.

## Accounts and authorization

Usernames are 3–32 ASCII letters, digits, dots, dashes or underscores, starting with a letter/digit; surrounding whitespace is removed and case is lowered consistently. Passwords are 12–1024 Unicode characters with a non-whitespace character. Passwords are never stripped or normalized.

Signup generates a random 32-byte **master key** for the database. `canonical_username + NUL + UTF-8 password` passes through Argon2id with a random 16-byte salt, 32-byte output, 65,536 KiB memory, three iterations, and four lanes. The derived key wraps the master key using AES-256-GCM. Associated data binds the format, purpose, username, and salt. A different username with the same password cannot unwrap it.

A separately salted Argon2id PHC password hash is stored inside encrypted SQLite. Login authenticates both the key wrapper and database image, then verifies the encrypted owner. Wrong credentials do not rewrite the file or create an account. No plaintext username index is stored.

Every service-level data, history, key-management, import and backup operation checks an open session and matching owner. Closing invalidates that session. This is owner authorization for one file, not isolation from an attacker controlling the running process; operating-system permissions still matter.

## Recovery and password changes

Signup generates a random 256-bit `SRK-` recovery token. Its bytes wrap the same master key using AES-256-GCM with a separate nonce and purpose-specific associated data. The token is shown for the user to save separately; no plaintext token is automatically stored on disk. Only the encrypted master-key wrapper is persisted.

Reset requires the username, recovery key and valid new password. It decrypts/authenticates the existing database, checks the owner, updates the encrypted password hash, and atomically saves new password **and recovery** wrappers. The RSA identity, item keys and history remain. The replacement recovery key must be saved; the old key fails on the updated file. Failed persistence leaves original credentials and recovery usable.

Normal password change requires the current password and keeps the recovery key valid. A logged-in owner can explicitly replace a lost recovery key using their current password, without changing that password. If both password and recovery key are lost, there is no reset bypass. Recovery cannot repair arbitrary ciphertext corruption.

Old backups retain their old passwords, recovery wrappers and private identity. Updating the current vault does not revoke separate copies. Create and verify a fresh encrypted backup after credential changes.

## Encrypted SQLite and format two

Only `sqlite3.connect(":memory:")` is used, with `temp_store=MEMORY`, `trusted_schema=OFF`, and bound SQL parameters. All SQLite pages, schema, and free pages are encrypted. No plaintext database, WAL, or journal is intentionally stored on disk. This is whole-image application encryption, not SQLCipher.

| Field | Size | Purpose |
| --- | --- | --- |
| `SVDB\x00\x02\r\n` | 8 bytes | Version identifier |
| Header length | 4-byte big-endian integer | At most 4,096 bytes |
| JSON credential header | Variable | KDF salt, password nonce/encrypted master key, recovery nonce/encrypted master key |
| Database nonce | 12 bytes | Fresh randomness for each save |
| Encrypted image and tag | Variable | AES-256-GCM under the random master key |

Identifier + length + exact JSON header is authenticated as database associated data. Password/recovery wrappers have their own authenticated contexts. Header parsing rejects unknown/duplicate fields and incorrect types/lengths. KDF settings are fixed by the version; untrusted inputs cannot request arbitrary KDF resource use. SQLite images are limited to 64 MiB.

The header exposes salts, nonces, encrypted wrappers, and overall size. Username, password hash, RSA keys, per-item keys, names and history remain encrypted. Wrapped master-key material is not a plaintext recovery token or exposed private key.

Saves write encrypted temporary files beside the destination, flush/fsync, and replace atomically. Failed mutations restore prior in-memory SQLite and credentials. An OS sidecar lock stays held for the session, and a fingerprint detects ordinary external changes before writing. Cooperative locking does not protect against malicious races or multiple machines ignoring each other's sync locks. Close a vault before syncing it.

On POSIX, directory fsync is attempted after publication. Hardware/filesystem behavior still imposes power-loss durability limits.

## File and message encryption

Version-one item formats stay compatible. Every item uses a new 32-byte AES-GCM key wrapped by the vault RSA-3072 public key with OAEP/SHA-256/MGF1-SHA-256 and a format-specific label. RSA public and PKCS#8 private DER and all per-item keys live inside encrypted SQLite.

Messages use `SEREIN1:` plus a URL-safe Base64 envelope. Files begin `SVFILE\x01\n`. Their bounded JSON headers contain version, type, random item ID, public-key fingerprint, nonce, and encrypted data key. The complete header is authenticated; names and plaintext are excluded. Credential changes preserve the RSA identity, so existing items remain recoverable.

Input files are never rewritten. Existing outputs are refused, including publication-time races. Encrypted Serein inputs are rejected for encryption. File keys save before output publication; publication failure can leave a harmless extra history record. Moving/renaming an encrypted file does not break its embedded key relationship.

File processing streams in 1 MiB chunks. Decryption writes temporary plaintext beside the output and publishes only after full authentication. Handled failures delete temporary files; abrupt termination may leave `.serein-*.tmp` files. Use trusted directories with appropriate account permissions. Deletion is not secure erasure, particularly on SSDs.

New file operations support cooperative cancellation between chunks and immediately before publication. Cancellation cannot retract an output already published; a cancelled encryption after key persistence can retain a harmless extra history entry. Progress reports byte counts through a bounded queue, without accessing Tk from the worker. Legacy Fernet operations retain their existing bounded whole-message behavior.

Optional message labels remain inside encrypted SQLite. History filtering reads authenticated metadata in memory and writes no plaintext search index. Relabeling uses the existing atomic transaction/rollback path and never changes the encrypted token. The read-only health check authenticates current storage, runs SQLite quick-check, validates the RSA identity, and reports counts/size; it does not attempt automatic repair.

Output publication uses same-directory atomic hard links. Unsupported filesystems fail while preserving the input. The vault itself uses atomic replacement for updates.

## Migration and UI

Password-only format-one vaults upgrade explicitly with the original password and a chosen username. An encrypted byte-for-byte backup is saved first. Existing identity/history survive. Old version-one backups retain password-only protection and need their own upgrade for current login.

Prototype Fernet imports validate complete batches and save inside encrypted SQLite. Original JSON/hash files remain unchanged until the user verifies recovery and decides how to handle them. Lost/overwritten prototype keys cannot be reconstructed from hashes.

The UI signs out after ten idle minutes and clears displayed secrets. Copying is explicit. App-owned clipboard values clear after 45 seconds, on sign out, or after confirming a saved recovery key if unchanged. Clipboard-manager/OS-history copies cannot be reliably removed by Tkinter. Workers never access Tk widgets.

Regression tests exercise account isolation, reset/rotation, failure injection, format-one upgrades, malformed inputs, tampering, key retention, backups, GUI flows, keyboard movement and palette contrast. These are not an independent cryptographic audit or formal screen-reader certification.

References: [PyCA Argon2id](https://cryptography.io/en/50.0.0/hazmat/primitives/key-derivation-functions/), [AES-GCM](https://cryptography.io/en/50.0.0/hazmat/primitives/aead/), [RSA-OAEP](https://cryptography.io/en/50.0.0/hazmat/primitives/asymmetric/rsa/), [SQLite serialization](https://docs.python.org/3.14/library/sqlite3.html#sqlite3.Connection.serialize).
