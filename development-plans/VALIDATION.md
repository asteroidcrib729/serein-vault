# Validation and academic readiness

**Version:** 1.2.0 · **Date:** 27 October 2026 · **Platform:** Windows 10 x64, build 19045<br>
**Environment:** CPython 3.14.7, uv 0.12.9, Tk 9.0.4, SQLite 3.50.4, native 200% display scale.

[README](../README.md) · [Completed work](development-plan-01.md) · [Remaining checks](development-plan-02.md) · [Packaging](PACKAGING.md)

## Automated and local acceptance checks

| Check | Observed result |
| --- | --- |
| Locked environment | `uv sync --locked --group packaging --offline` passed; `.venv` is Python 3.14.7 |
| Dependency lock | `uv lock --check --offline` passed |
| Source quality | Ruff lint and format checks passed |
| Regression suite | **117 passed**, with a real Windows Tk display; no display-skipped tests in this run |
| Advisory audit | Installed environment: 47 third-party distributions; no known vulnerabilities reported |
| Workflow syntax | All GitHub Actions workflows passed actionlint |
| Source/wheel packaging | Source distribution, wheel, and wheel built from the source archive passed |
| Independent wheel runtime | Isolated wheel environment checks signup, message/file recovery, health, encrypted backup/restoration and actual Tk startup |
| GUI visuals | Fresh signup, Messages and Files screenshots reviewed; native 200% text rendering, dark controls, visible status and focus |
| Window/scaling behavior | Minimum 840×660 window; focused controls/actions reachable with simulated 125%, 150%, 200% Tk font scaling |
| Precision input | Generated Tk 9 TouchpadScroll events and small/zero MouseWheel deltas exercised on a real form; native message Text scrolling retained |
| EXE runtime | Frozen and installed application probes passed using synthetic vaults only |
| EXE installer | Per-user install, actual installed Tk/backend probe, uninstall, and separate user-data sentinel preservation passed |
| MSIX preview | MakeAppx schema validation, archive identity/payload checks, every payload block hash, and extracted runtime probe passed |
| Runtime origin/licensing | Frozen DLL sources restricted to Python/environment/Windows; MIT author credit and upstream notices included |
| Editor configuration | Windows `.venv` executable exists and imports application/Tk/crypto; debugger explicitly uses it; pytest discovery and Ruff formatter configured |
| Legacy archive | Original executable/report retained as deprecated archives and excluded from current distributions |

The first-party `serein-vault` package is not published on PyPI, so the advisory service skips it; tests cover that source directly. The audit includes the installed development/build tools. A clean result concerns known package advisories at check time and does not establish that every application vulnerability is absent.

## What the tests cover

Account tests exercise signup/login, username normalization, wrong credentials, owner authorization, recovery-key reset/replacement, failed-reset rollback, password-only upgrades with backups, password changes, and old-backup credential behavior. Storage checks cover full-database encryption, private/public keys and hashes, locking/competing processes, external changes, size bounds, atomic-save rollback, safe backups, and no implicit overwrites.

Crypto and filesystem checks cover exact Unicode/whitespace, key retention, moved files, message/file tampering and truncation, output races, preserved inputs, legacy imports/recovery, streaming progress, empty/multichunk files, cancellation before work/between chunks/after key save/before publication, and usable vaults after failures. There are 128 deterministic malformed-envelope samples. Label/filter tests cover Unicode case folding, literal search, encrypted persistence, backup/reopen, validation, restricted file relabeling, authorization, and failed-save rollback.

GUI tests use actual Tk widgets and the worker loop for account creation/recovery acknowledgment, login/reset, message/file roundtrips, damaged-file rejection, history search, health, idle sign out, clipboard ownership, Tab events, precision scroll events, bounded progress updates, cancellation, minimum dimensions, and simulated scaled fonts. Palette contrast meets the tested 4.5:1 text and 3:1 focus/field-boundary targets. Release verification deliberately corrupts fixtures to prove checksum/MSIX block mismatches are detected.

## Installer evidence

Each successful build writes `frozen-smoke.json`, optional `msix-payload-smoke.json`, `provenance.json`, `SHA256SUMS.txt`, and `Analysis-00.toc` under its timestamped `packaged-releases/` directory. EXE install tests add `installed-smoke.json` and `installer-validation.json`; refresh and verify checksums afterward. Provenance records current Git head **and dirty working-tree state**, plus exact source file hashes. Those original local artifacts predate Git delivery. Hosted build provenance records the subsequently committed source and must be clean before draft upload.

The first sandboxed installer attempt was correctly rolled back after Windows denied Start Menu/registry writes. The controlled per-user installation test then passed outside that restricted filesystem sandbox and removed its installation. No personal vault or credential file was opened or generated.

## Explicit remaining boundaries

- Hosted validation and build/draft workflows are configured; the delivery section below will record observed runs, assets and results after push.
- The EXE and MSIX are unsigned. MSIX extraction/startup does not test trusted Windows package installation, package identity, storage virtualization, updates, or uninstall.
- No production certificate, trust-store change, Store certification or public release is claimed. Commit/push and unpublished drafts are authorized for the 27 October delivery.
- The frozen/installed tests ran on the development machine. A separate machine without Python remains an acceptance step.
- Physical two-finger driver behavior, mixed-monitor DPI changes, a separate human keyboard walkthrough, and NVDA/screen-reader announcements remain unverified. The available evidence tests the actual Tk precision event path and font scaling, not all hardware/assistive technology.
- This is a simple local academic application. There has been no independent cryptographic security audit.

The original foundation passed 53 tests; account work expanded that to 74, and version 1.2 expands it to 104. These results support local academic/demo use with the stated limits.


## Root directory rename verification - 26 October 2026

The local root was renamed from `encryption-tool-python` to `serein-vault`. Verification reproduced a stale editable-install path (`ModuleNotFoundError`) and stale executable launchers (`uv trampoline failed to canonicalize script path`). uv regenerated the environment's editable installation and all locked launchers with `sync --locked --group packaging --reinstall --offline`. `uv venv --allow-existing` also regenerated activation scripts while preserving installed packages.

The actual documentation directory is lowercase `development-plans`; README links, the source-distribution include list, build provenance collection, and related references now match that spelling for case-sensitive systems. The local rename does not rename the GitHub repository; its existing remote/publisher URL is retained.

Repeated GUI validation exposed a separate Tk interpreter-ownership edge case: an icon could be created in another root's default interpreter. Images and all Tk variables now explicitly belong to their `VaultApp`. A two-root regression checks image ownership and independent form state. GUI fixtures skip only genuine display-unavailability errors; widget/image initialization errors now fail instead of being silently skipped.

Final regression result: **105 passed, zero skipped**. Ruff lint/format, dependency compatibility, lock consistency, VS Code paths/PowerShell activation, and Markdown links/casing passed. Module launch, the generated GUI launcher, and `main.py` each passed real Tk and synthetic message/file/health/backup-restoration probes. Source/wheel and EXE/MSIX builds were repeated from the renamed root; frozen and extracted-MSIX probes and package checks passed.

The shared pytest temporary/cache directories had Windows permission errors, so validation used fresh run-specific directories under ignored `.packaging-build/`. No global temporary-directory permissions were changed. Dependency versions and `uv.lock` are unchanged. Existing user data and archived artifacts were preserved. Earlier build reports retain their original absolute paths as historical evidence; fresh builds record `serein-vault`.

Reports for this relocation are stored locally under `.packaging-build/rename-validation-2b4407b93e86/`; fresh installers and their provenance/checksums are under `packaged-releases/`. Unsigned MSIX, hosted CI, signing, independent-machine, and physical accessibility boundaries stated above still apply.


## Academic delivery and draft releases - 27 October 2026

**Assessment:** repaired, improved, modernized and academically validated for desktop demonstration/review. [Academic readiness](ACADEMIC-READINESS.md) defines the implemented scope and remaining acceptance boundaries.

Both installer workflows now expose build -> draft jobs. Drafts require exact clean-source provenance, complete checksums, licensing/credit and successful runtime evidence; uploads are checked against GitHub file digests/sizes. Pull requests never create drafts. Current CI does not commit code; its Git defaults name Faraz Hussain as author and github-actions[bot] as committer for any future workflow Git commit.

Local validation passed **117 tests, zero skipped**, including twelve draft safety checks, on 27 October 2026. Ruff, formatting, actionlint, documentation links/casing, lock consistency and installed dependency compatibility passed before committing the pending modernization. Hosted delivery evidence is pending the first authorized push and will be recorded here after actual runs and attached assets are inspected. A draft is an unpublished academic preview, not a signed/public end-user release.
