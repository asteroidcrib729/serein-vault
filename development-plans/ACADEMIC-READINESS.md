# Academic readiness

**Assessment: academically validated desktop application.**<br>
**Project:** Serein Vault 1.2.0 | **Reviewed:** 27 October 2026

[README](../README.md) | [Validation evidence](VALIDATION.md) | [Completed work](development-plan-01.md) | [Remaining checks](development-plan-02.md)

The original academic project has been repaired, improved, and modernized for academic demonstration, source-code study, and review. The implemented scope is one local owner per encrypted vault, with a Tkinter desktop interface and no server.

## Completed academic scope

- Python 3.14.7, uv, object-oriented application boundaries, and a locked dependency set.
- Encrypted SQLite images holding account details, password hashes, RSA identity, item keys, and history.
- Username/password signup and login, owner authorization, recovery-key reset and replacement.
- Authenticated message/file protection, preserved input files, atomic output publication, rollback, backups, and explicit legacy imports.
- Dark Tkinter UI, DPI-aware rendering, precision scrolling, keyboard navigation, labels/search, byte progress, safe cancellation, and read-only health checks.
- MIT licensing, original-author and academic acknowledgments, migration/security/dependency guides, regression tests, and source/installer packaging.

Hosted Windows and Linux each passed all **117 tests without skips**, advisory audits and distribution builds. Hosted EXE/MSIX build -> draft jobs passed; the downloaded installers and every release asset were checked against provenance/checksums. [Exact run evidence](VALIDATION.md#verified-hosted-delivery) identifies the source commit and drafts.

The validation record separates local test results from hosted jobs and hardware checks. Passing checks support the academic assessment; they do not prove the absence of every defect.

## Distribution and automation

The EXE and MSIX workflows each expose separate build and draft jobs. Drafts are unpublished academic previews pinned to the built commit. They include the installer, source provenance, checksums, license/credit and successful runtime evidence. Pull requests build without permission to create releases.

Drafts do not mean signed installers or public releases. The workflows do not create code commits. Their configured Git author is Faraz Hussain and their committer is github-actions[bot] for any future workflow Git operation. Ordinary local commits retain the developer's Git identity.

## Remaining acceptance boundaries

- Production signing and trusted MSIX installation/update/uninstall.
- Independent clean-machine acceptance without development Python.
- Physical touchpad/driver, mixed-monitor DPI, a separate human keyboard walkthrough, and screen-reader announcements.
- Independent cryptographic assessment or accessibility certification, if a future use case requires them.
- Public release publication after human review; draft creation does not publish.

Cloud sync, shared-user administration, email resets and recipient key exchange remain outside this simple academic project.

A suitable description is: **"A repaired and modernized academic desktop application, validated through automated backend, GUI, and packaging tests."**
