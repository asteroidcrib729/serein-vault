# Development Plan 01 — Completed Work

**Project:** Serein Vault · **Current version:** 1.2.0 · **Recorded:** 26 October 2026<br>
**Purpose:** document the work completed from the original academic repository through the current local-account desktop application.<br>
**Status:** repaired and modernized for academic demonstration/review; local validation complete. Git delivery and hosted build/draft verification are tracked in [validation](VALIDATION.md).

[README](../README.md) · [Future plan](development-plan-02.md) · [Validation](VALIDATION.md) · [Security design](SECURITY.md)

## Section 01 — Original Repository Scan

- [x] Read the original 386-line Tkinter source and six-page academic report.
- [x] Inventory the four tracked artifacts: source, Windows executable, password-hash file, and report.
- [x] Identify plaintext key storage and the password's limited role as an interface gate.
- [x] Reproduce message-key replacement, repeated file-encryption key loss, overwrite-before-key-save failure, filename-dependent recovery, and inconsistent password handling.
- [x] Confirm that message decryption ignored its text input and that encryption stripped plaintext whitespace.
- [x] Identify absent dependency management, tests, CI, current documentation, and reproducible packaging.

The initial scan used isolated sample data. No real encrypted files or private keys were found for automatic migration. Surviving user data must be imported explicitly rather than guessed or overwritten.

## Section 02 — Project Identity and Legacy Preservation

- [x] Rename the application/package to **Serein Vault** while retaining the existing repository directory and Git history.
- [x] Replace root `main.py` with a small supported launcher.
- [x] Archive the original source as `legacy/main.py.txt`.
- [x] Archive the old executable as `legacy/main.py.exe.deprecated` to prevent ordinary executable launch.
- [x] Archive `Project Report.pdf` and mark it deprecated, superseded by current documentation.
- [x] Verify that archived executable/report SHA-256 hashes match their originals.
- [x] Remove the prototype's tracked plaintext password hash from the active tree.
- [x] Exclude deprecated artifacts and local data from current distributions.

Evidence: [legacy archive record](../legacy/README.md), [launcher](../main.py), [project metadata](../pyproject.toml).

## Section 03 — Python Environment and Dependency Audit

- [x] Create a project-local Python **3.14.7** `.venv` using **uv**.
- [x] Add `.python-version`, `pyproject.toml`, and an exact `uv.lock`.
- [x] Keep PyCA `cryptography` as the only direct runtime dependency; verify compatible version **50.0.2**.
- [x] Replace `pyperclip` with standard Tkinter clipboard access.
- [x] Replace unsalted fast password hashing with Argon2id.
- [x] Use standard-library SQLite, filesystem, JSON, threading, and encoding facilities.
- [x] Lock pytest, Ruff, pip-audit, and the Hatchling build backend; include the pinned backend in advisory checks.
- [x] Ignore virtual environments, caches, local credentials, vaults, encrypted files, and build output in Git.

Evidence: [dependency audit](DEPENDENCIES.md), [project metadata](../pyproject.toml), [lockfile](../uv.lock).

## Section 04 — Encrypted Storage and Safe Item Operations

- [x] Replace plaintext key JSON storage with fully encrypted SQLite images.
- [x] Keep SQLite in memory while unlocked; write encrypted images rather than plaintext database/WAL/journal files.
- [x] Store account details, password hash, RSA public/private identity, item keys, and history inside encrypted SQLite.
- [x] Use Argon2id and AES-256-GCM for credential and database protection.
- [x] Generate an RSA-3072 identity and wrap fresh item keys using OAEP/SHA-256.
- [x] Authenticate versioned, bounded message/file headers and reject malformed inputs.
- [x] Preserve original files and refuse existing outputs, including races during publication.
- [x] Persist file recovery records before publishing encrypted outputs.
- [x] Stream new file operations in 1 MiB chunks and publish decrypted output only after authentication.
- [x] Reject accidental repeated encryption of Serein-encrypted files.
- [x] Recover renamed/moved files without depending on saved absolute paths.
- [x] Retain every successful message record and preserve exact Unicode/whitespace.
- [x] Add atomic saves, in-memory rollback on persistence failure, process locking, and external-change detection.
- [x] Add encrypted backups and an explicit 64 MiB database-image limit.

Evidence: [storage](../src/serein_vault/storage.py), [cryptography](../src/serein_vault/crypto.py), [filesystem safety](../src/serein_vault/filesystem.py).

## Section 05 — Username/Password Accounts and Recovery

- [x] Replace the active password-only interface with **signup, login, reset, and sign out**.
- [x] Keep the model simple: one local owner per selected vault, without servers, email, or multiple role types.
- [x] Normalize/validate usernames consistently and preserve passwords exactly.
- [x] Cryptographically bind username and password to the password-wrapped random vault key.
- [x] Store the username and salted password hash inside encrypted SQLite.
- [x] Check an authenticated owner session before all service data/key/import/backup operations.
- [x] Generate a random 256-bit recovery key at signup; show it without automatically persisting plaintext.
- [x] Require acknowledgment that the recovery key was saved before continuing.
- [x] Reset forgotten passwords using username and recovery key while retaining identity, files, and history.
- [x] Rotate the recovery key after a successful reset.
- [x] Let a logged-in owner replace a lost recovery key using the current password.
- [x] Keep recovery valid through an ordinary current-password change.
- [x] Ensure failed resets and failed credential writes preserve existing credentials and data.
- [x] Upgrade password-only version-one vaults with a separate encrypted original backup before replacement.

Evidence: [account envelope](../src/serein_vault/accounts.py), [authorized service](../src/serein_vault/service.py), [account regressions](../tests/test_accounts.py).

## Section 06 — Tkinter Interface, Accessibility, and Ergonomics

- [x] Use **Tkinter/ttk only**, with a dark palette, clearer spacing, larger text, and consistent actions.
- [x] Add fixed signup/login/reset navigation and scrollable account forms.
- [x] Provide persistent labels, masked secret entries, and an explicit visibility control.
- [x] Show expected failures inline with an `Error:` prefix rather than repeated modal dialogs.
- [x] Add visible keyboard focus, logical Tab movement through message areas, shortcuts, and F1 help.
- [x] Check regular-text contrast against 4.5:1 and focus/field boundaries against 3:1 design targets.
- [x] Add explicit input/output path controls for file operations.
- [x] Reserve space for message/history actions and status feedback at minimum window size.
- [x] Scroll account/file forms and bring focused controls into view.
- [x] Switch to Messages after loading/recovering a history message.
- [x] Run expensive operations in one worker while updating widgets only on Tk's main thread.
- [x] Add an activity indicator, ten-minute idle sign out, and display clearing on sign out.
- [x] Make clipboard copying explicit; clear unchanged app-owned values after 45 seconds or sign out.
- [x] Capture current signup, message, and file screenshots for documentation.

Automated contrast and keyboard checks do not establish full screen-reader accessibility. Physical touchpad, assistive-technology, and mixed-monitor checks remain in Plan 02.

## Section 07 — Legacy Import and Migration

- [x] Validate complete legacy JSON batches before an atomic encrypted import.
- [x] Support pretty-printed file-key JSON, moved legacy files, and saved legacy messages.
- [x] Archive an explicitly selected old password hash inside encrypted SQLite.
- [x] Preserve import sources and write recovery outputs separately.
- [x] Bound legacy JSON imports to 10 MiB/10,000 records and old Fernet file recovery to 64 MiB input.
- [x] Explain that missing/overwritten legacy keys cannot be reconstructed from password hashes.

Evidence: [migration guide](MIGRATION.md), [legacy importer](../src/serein_vault/legacy.py).

## Section 08 — License and Documentation

- [x] Add the standard **MIT License** with credit to **Faraz Hussain and contributors**.
- [x] Include license metadata and license files in packaging.
- [x] Retain academic acknowledgments for Tameem Zahid, Faraz Hussain, and Muhammad Abbas.
- [x] Explain the notice-preservation requirement without inventing additional nonstandard license restrictions.
- [x] Expand README coverage of setup, features, accounts, recovery, use, backups, shortcuts, architecture, migration, tests, and licensing.
- [x] Refresh security, migration, dependency, and validation documentation.
- [x] Create this completed-work record and a separate future-work plan.

Evidence: [LICENSE](../LICENSE), [AUTHORS](../AUTHORS.md), [README](../README.md), [Plan 02](development-plan-02.md).

## Section 09 — Verification and Delivery Boundaries

- [x] Run the complete current regression suite: **117 passed**, including real Tkinter flows.
- [x] Pass Ruff lint and formatting checks.
- [x] Check source, environment and dependency-lock consistency.
- [x] Configure Windows/Linux GitHub Actions for sync, tests, lint, audit and packaging.
- [x] Preserve the earlier successful dependency-audit and isolated-wheel validation workflow and rerun release checks for the current build; see the final [validation record](VALIDATION.md).

The original foundation had 53 tests; accounts expanded it to 74, and desktop, usability, cancellation, and artifact verification expanded it to 104. The project's current status is suitable for **local academic/demo review**. Hosted CI, signed installer delivery, independent cryptographic assessment, and formal screen-reader testing are separate activities, not implied by local tests. That initial local phase did not commit/push or publish. The 27 October delivery stage below records the subsequently authorized Git/CI/draft work.

## Section 10 — Version 1.2 Desktop and Distribution Work

- [x] Apply a dark navy/teal interface, sharper DPI-aware rendering, adaptive initial window dimensions, and multi-resolution branding.
- [x] Fix form scrolling for Tk 9 precision touchpad events and small wheel deltas; retain native scrolling inside text/history widgets.
- [x] Add encrypted message labels/editing and local history filtering.
- [x] Add byte progress and cooperative cancellation with source preservation, temporary cleanup, and failure-path tests.
- [x] Add authenticated read-only vault health checks and deterministic malformed-envelope tests.
- [x] Configure EXE and MSIX CI workflows using one shared locked builder, plus monthly dependency review.
- [x] Build local installers under `packaged-releases/`, record source/artifact hashes, and check binary origins and upstream notices.
- [x] Exercise frozen and installed GUI/backend behavior, EXE install/uninstall, MSIX block hashes, and extracted runtime startup.
- [x] Finalize AUTHORS wording and consolidate all former `docs/` material into `development-plans/`.
- [x] Repair VS Code interpreter, debugger, test discovery, and formatter configuration.
- [x] Refresh documentation and screenshots after implementation and local acceptance checks.

See [Plan 02](development-plan-02.md) for the feature-by-feature acceptance record and remaining hardware, hosted-run, signing, and release boundaries.


## Section 11 - Root Rename Verification and Repair

- [x] Verify the local root at `serein-vault` and reproduce broken editable imports and Windows launchers.
- [x] Regenerate uv activation scripts, editable installation and launchers without changing locked versions.
- [x] Match documentation/build references to the actual lowercase `development-plans` directory.
- [x] Verify VS Code interpreter/debug paths and actual PowerShell environment activation.
- [x] Fix the Tk interpreter-ownership edge case exposed during repeated GUI startup; add a two-root regression and reject unexpected GUI initialization skips.
- [x] Pass all 105 backend/GUI tests with no skips, lint/format, dependency compatibility and lock checks.
- [x] Verify every documented launch path, source/wheel builds, fresh EXE/MSIX builds, package checksums and synthetic runtime probes.
- [x] Preserve `uv.lock`, personal data, existing historical installers/reports, and original archived artifacts.

See the root-rename section of [validation](VALIDATION.md) for the exact repair and evidence limits. No GitHub rename, commit, push or public release was performed.


## Section 12 - Academic Readiness and Draft Delivery, 27 October 2026

- [x] Record academically validated status with explicit signing, independent-machine, hardware/accessibility and security-audit boundaries.
- [x] Refresh all current guides and acknowledgments while preserving MIT terms and historical results.
- [x] Add separate build -> draft jobs to both installer workflows with scoped release-write permissions and no drafts on pull requests.
- [x] Require clean exact-source provenance, checksums and successful smoke/install evidence before creating unpublished drafts; verify uploaded file digests/sizes.
- [x] Configure Faraz Hussain as workflow Git author and github-actions[bot] as committer. Current workflows do not create code commits.
- [x] Align Git remote and installer links with the existing canonical GitHub repository name serein-vault.
- [ ] Commit/push the complete pending modernization and inspect hosted Windows/Linux validation, installer artifacts and draft releases. Completion evidence belongs in [validation](VALIDATION.md).
