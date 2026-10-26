# Windows installers

[README](../README.md) · [Validation](VALIDATION.md) · [Remaining work](development-plan-02.md)

The current application is Serein Vault 1.2.0. The archived `main.py.exe` is never used to produce these installers. All build commands below run from the repository root on **x64 Windows**.

## Build locally

Install uv and the Windows 10/11 SDK with MakeAppx. Then run:

```powershell
uv python install 3.14.7
uv --cache-dir .uv-cache sync --locked --group packaging
uv --cache-dir .uv-cache run --locked --group packaging python packaging/build_windows.py
```

Use `--format exe` or `--format msix` to build one format. The EXE build bootstraps a project-local **Inno Setup 7.1.0** compiler from the official release after checking its pinned SHA-256 and Authenticode publisher. An existing trusted compiler can be supplied with `--inno C:\path\ISCC.exe`. Inno Setup's own licensing applies to the build tool; see its [upstream license](https://jrsoftware.org/files/is/license.txt) and [commercial-use guidance](https://jrsoftware.org/isinfo.php).

Each build creates a new timestamped subdirectory in **`packaged-releases/`**. It contains the EXE setup and/or unsigned MSIX, frozen smoke evidence, MSIX payload smoke evidence when applicable, `SHA256SUMS.txt`, `provenance.json`, the binary analysis record, MIT license, and author acknowledgment. Intermediate freezing/staging directories stay in `.packaging-build/`. Both roots are ignored in Git. A failed build can leave an incomplete directory; use a build only when its provenance/checksums and all requested checks exist and pass.

PyInstaller freezes one maintained source entry point and the locked runtime dependencies. The application has no runtime dependency on Pillow, PyInstaller, pytest, or uv. Pillow only generates multi-resolution branding assets. The build removes unrelated application directories from its freezing PATH and checks binary origins against the project environment, base interpreter, and Windows directory.

Tcl/Tk scripts and notices can live in Tk 9's embedded zip filesystem. The build reads the license notices through Tcl rather than assuming a physical `tcl/` directory. Python, PyCA, cffi, pycparser, and PyInstaller notices are included as well.

## Verify an EXE installation

The setup installs per user under `%LOCALAPPDATA%\Programs\SereinVault`, creates a Start Menu entry and uninstall registration, and requires no administrator rights. Vaults normally live in the separate `%LOCALAPPDATA%\SereinVault` data directory. Uninstall does not delete that directory or user-selected vaults/files.

To exercise a newly generated setup with synthetic data:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File packaging/test_installer.ps1 -Installer "packaged-releases\<build>\SereinVault-1.2.0-windows-x64-setup.exe" -EvidenceDirectory "packaged-releases\<build>"
uv run --locked --group packaging python packaging/verify_release.py "packaged-releases\<build>" --refresh-checksums
```

The test refuses to replace an existing EXE installation. It installs into a unique directory inside `.packaging-build/`, launches real Tk with a disposable account, checks message/file roundtrips, integrity, backup restoration, then uninstalls and checks a separate synthetic user-data sentinel. Windows must allow normal per-user shortcut/registry writes. Its execution-policy override applies only to that PowerShell process.

Each application executable also accepts an explicit `--smoke-test <new-report.json>` probe. It uses a temporary synthetic vault, never opens a personal vault, and writes a report only after successful checks. Normal launch remains GUI-only.

## MSIX signing boundary

The generated **`-unsigned.msix` is a preview package**. MakeAppx performs schema validation; the Python verifier checks every payload block against the block map. An extracted payload also runs the same real Tk/backend smoke test. Extraction does not exercise Windows package identity, installation, storage virtualization, update, or uninstall behavior.

For installation, use a valid signing certificate with a subject matching manifest publisher **`CN=Faraz Hussain`**, or deliberately update the publisher to match your release identity before building. Use the Windows SDK SignTool with SHA-256 and an appropriate timestamp service, verify the signature, and regenerate checksums/provenance for the signed artifacts. Keep certificate private keys outside the repository. This workflow does not generate self-signed identities, install root certificates, change Developer Mode, or claim Store certification.

Signing and a trusted MSIX installation are still required before treating it as an end-user release. The EXE is also unsigned; local functional tests do not establish publisher reputation or remove Windows signature prompts.

## GitHub Actions

- [EXE workflow](../.github/workflows/windows-exe.yml): manual dispatch, main/tag pushes, and relevant pull requests.
- [MSIX workflow](../.github/workflows/windows-msix.yml): the same triggers, producing unsigned previews.
- [Shared builder](../.github/workflows/windows-package.yml): Windows 2025 runner, pinned actions and uv, Python 3.14.7, locked dependencies, lint/format/tests/advisory audit, package build, EXE installation check when applicable, final checksum/MSIX verification, and artifact upload.
- [Validation workflow](../.github/workflows/ci.yml): Windows plus Linux with an Xvfb Tk display.

Build the checked-out source; no version string is treated as a Git ref. Local provenance records dirty trees explicitly. CI drafts require a clean tree and the exact built Git SHA. Hosted Windows/Linux validation and both installer build/draft workflows have passed. Per-commit results and artifact/draft links are reported in GitHub Actions; [verified hosted delivery](VALIDATION.md#verified-hosted-delivery) records the inspected source, jobs, assets and unsigned boundary.

References: [PyInstaller requirements](https://pyinstaller.org/en/stable/requirements.html), [MakeAppx](https://learn.microsoft.com/en-us/windows/msix/package/create-app-package-with-makeappx-tool), [Windows DPI awareness](https://learn.microsoft.com/en-us/windows/win32/hidpi/setting-the-default-dpi-awareness-for-a-process), [Tk precision scroll events](https://www.tcl-lang.org/man/tcl9.0/TkCmd/bind.html).


## Build -> draft behavior

The EXE and MSIX entry workflows each have a read-only **build** job followed by a **draft** job with contents-write permission. The draft job downloads only the successful build's uniquely named artifact. Pull requests cannot run the draft job. Main/tag pushes enable drafts; manual dispatch has a create_draft checkbox, default true.

`packaging/create_draft.py` checks source SHA, clean-tree state, format, version, licensing/author credit, complete checksums, installer digests and successful runtime reports before creating a release. EXE drafts require the installed-app and install/uninstall reports. MSIX drafts require extracted-runtime evidence. GitHub's uploaded sizes/digests are verified too.

Draft tags use `preview-<format>-<12-character SHA>-<run ID>-<attempt>`. Formats and retries do not overwrite one another. Every draft targets the full built commit, stays draft/prerelease, and is never automatically published or marked latest. Reports/source hashes remain attached. If an upload fails, a partial unpublished draft can remain; inspect that failed run instead of treating it as ready. A rerun creates a separate attempt-specific draft.

The draft uploader uses the runner's standard-library Python for release infrastructure; the application/build/test jobs use the pinned Python 3.14.7 uv environment. No release token, personal vault or signing key is included in build artifacts. The upload token is scoped only to the draft step.

No current workflow makes code commits. Any future workflow Git commit must use Faraz Hussain as author and github-actions[bot] as committer; those environment defaults are configured in every workflow. Draft release metadata/tag selection does not create a code commit. Public publication, production signing and certificate trust changes remain manual acceptance steps.

[Academic readiness](ACADEMIC-READINESS.md) ? [GitHub release API](https://docs.github.com/en/rest/releases/releases#create-a-release)


Hosted portability: the bootstrap prefers PowerShell 7 to match the runner. Its Windows PowerShell fallback uses a native module path, and SHA-256 verification uses .NET directly. This avoids inheriting incompatible PowerShell 7 module paths into a PowerShell 5 child. Signature/publisher verification remains mandatory. The Windows GUI uses the native ICO loader; other desktop platforms use a Tk-owned PNG image.
