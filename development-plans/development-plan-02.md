# Development Plan 02 — Implemented Improvements and Remaining Checks

**Project:** Serein Vault · **Current version:** 1.2.0 · **Updated:** 27 October 2026<br>
**Status:** academically validated for local demonstration/review. Bounded usability, maintenance, and installer work is implemented; unpublished draft delivery and hosted verification are now authorized. Unchecked acceptance items remain explicit.

[README](../README.md) · [Completed work](development-plan-01.md) · [Validation](VALIDATION.md) · [Windows packaging](PACKAGING.md)

## Section 01 — Keep the Academic Scope

- [x] Retain one local owner per encrypted vault, Python 3.14.7, uv, OOP, and Tkinter/ttk only.
- [x] Keep PyCA cryptography as the only direct runtime dependency.
- [x] Reuse existing authenticated storage, item envelopes, recovery, and backup classes; no new server or authentication provider.

## Section 02 — Accessibility and Desktop Behavior

- [x] Replace the light interface with a consistent dark navy palette, teal primary actions, readable text, and visible focus/field boundaries.
- [x] Enable Windows PerMonitorV2 DPI awareness before Tk creation and declare it in the frozen executable manifest. Size the initial window for the actual screen/scaling.
- [x] Generate a multi-resolution icon at build time; render the interface with native Tk text and controls.
- [x] Handle Tk 9 `TouchpadScroll` events and accumulated small `MouseWheel` deltas on forms before Entry bindings consume them. Preserve native Text/Treeview scrolling.
- [x] Exercise actual generated Tab, wheel, and precision-touchpad events against real Tk windows.
- [x] Check focus visibility and minimum-window actions with simulated 125%, 150%, and 200% font scaling; review screenshots on the actual Windows 200% display.
- [x] Exercise signup, recovery acknowledgment, login/reset, file processing, history, backup restoration, and sign out with automated GUI/backend checks.
- [ ] Complete a separate human keyboard-only walkthrough and physical two-finger touchpad check. Synthetic events verify the Tk event path, not the specific touchpad driver.
- [ ] Test NVDA/screen-reader announcements and focus feedback. NVDA was not available in this environment; do not claim certified support.
- [ ] Verify physical monitor changes and mixed-DPI monitor movement. Simulated Tk scaling does not replace these hardware checks.
- [ ] Complete the authorized Git delivery and inspect hosted Windows/Linux CI, installer artifacts and unpublished drafts; record actual run URLs/results in validation.

## Section 03 — Small Usability Features

| Improvement | Implemented behavior | Acceptance evidence |
| --- | --- | --- |
| Local history search | Case-insensitive literal filter over type, label, and date; metadata remains encrypted on disk | Unicode case folding, missing matches, GUI filtering, no plaintext index |
| Message labels | Optional labels up to 80 characters; edit a selected message label | Validation, encrypted persistence, backup/reopen, failed-save rollback, unchanged plaintext/token |
| File progress | Byte totals and percentage from streaming operations through a bounded queue | Monotonic backend updates, responsive real Tk polling, no worker access to widgets |
| Safe cancellation | Check cancellation between chunks and before publication, clean handled temporary outputs | Before-start, middle, final-chunk, and post-key-save cancellation tests for original preservation and usable vaults |

- [x] Keep the controls in the existing Messages, Files, History, and Account tabs.
- [x] Refresh screenshots and usage guidance after acceptance checks.

Cancellation is cooperative. If publication has already completed, a late click cannot retract the saved output. Cancellation after persisting a recovery key can retain a harmless extra history record. Legacy Fernet import/recovery remains bounded and does not offer streaming cancellation.

## Section 04 — Maintenance and Data Safety

- [x] Configure monthly Dependabot review for uv and GitHub Actions dependencies; updates still require locked resolution, tests, and advisory checks.
- [x] Add an authenticated, read-only health check: SQLite quick-check, RSA identity validation, record count, and encrypted file size. It makes no repair guesses and does not rewrite the vault.
- [x] Add 128 deterministic malformed-envelope samples and focused label/cancellation failure injection.
- [x] Exercise encrypted backup restoration with the source identity and messages, including frozen and installed application probes.
- [x] Explain fresh backups after password/recovery changes and preserve separate copies' original credentials.
- [x] Fix workspace interpreter/debug/test/formatter settings and verify the local Python 3.14.7 `.venv`.

## Section 05 — Windows Distribution

- [x] Freeze the current locked source with PyInstaller 6.22.3, build per-user EXE installers with Inno Setup, and build MSIX previews with Windows SDK MakeAppx.
- [x] Keep generated local installers and evidence under ignored `packaged-releases/`, with separate isolated intermediate work under `.packaging-build/`.
- [x] Exclude archived coursework executables/report, personal data, development dependencies, and environments from the runtime payload.
- [x] Retain MIT author credit and bundled upstream license notices.
- [x] Restrict the freezing PATH and reject unexpected binary origins using the PyInstaller analysis record.
- [x] Generate artifact SHA-256 checksums and provenance with the source file hashes, Git head, dirty state, interpreter, build-tool version, and unsigned status.
- [x] Validate the frozen GUI/backend, MSIX schema and payload block hashes, and an extracted MSIX runtime.
- [x] Install/probe/uninstall the EXE in a disposable location and verify separate synthetic user data survives uninstall.
- [x] Add EXE/MSIX GitHub Actions entry workflows and a shared builder; upload reviewed artifacts with their evidence.
- [ ] Provide a production signing certificate whose subject matches the MSIX publisher, sign the packages, and test MSIX installation/update/uninstall under a trusted identity.
- [ ] Verify on a clean Windows machine without development Python installed. The current frozen/installed tests run on the development machine.
- [x] Implement source-pinned, checksum-verified unpublished draft creation with separate build -> draft jobs.
- [ ] Publish a public release only after review and a separate explicit request. Draft creation is authorized; signing/trust-store changes remain outside this delivery.

## Section 06 — Intentionally Outside This Academic App

Cloud synchronization, shared multi-user vaults, administrator roles, email/SMS resets, OAuth, browser frontends, remote databases, recipient public-key exchange, and plugin systems remain outside scope. They would need a separate explicit design and use case.

The deprecated `main.py.exe` and `Project Report.pdf` stay archived. New installers come from the current source and lockfile.
