# Dependency audit

Documentation review: **27 October 2026**. Academic readiness is recorded in [the assessment](ACADEMIC-READINESS.md). Draft publishing uses standard-library HTTP/JSON/hash verification and adds no application dependency. The 26 October package audit remains a dated result; hosted audit jobs run for each delivery.

Audit date: **26 October 2026**. Target interpreter: **CPython 3.14.7**. The prototype had no manifest or pinned dependency versions, so its original installed versions and executable's bundled dependencies cannot be established from source alone.

Version 1.1 adds local accounts, recovery-key resets, MIT licensing and the updated Tkinter interface without adding a runtime dependency. Account wrapping reuses AES-GCM and Argon2id from the already locked PyCA package. There is no email, authentication service, server framework or extra GUI toolkit.

Version **1.2** retains that runtime boundary. An optional **packaging** dependency group locks **PyInstaller 6.22.3** and **Pillow 13.0.0** for Windows freezing and build-time icon generation. Pillow is not imported by the application or included as an application dependency. Tcl/Tk, ctypes DPI support, event routing, progress queues, cancellation, search, and health checks use the standard library.

Windows installers use **Inno Setup 7.1.0** and the installed **Windows SDK MakeAppx** tool, outside Python's runtime dependency set. The compiler bootstrap verifies its official download hash and publisher. Review upstream build-tool licensing separately from the project's MIT license. [Packaging instructions](PACKAGING.md) describe artifact checks and the unsigned MSIX boundary.

The current installed environment has **47 third-party distributions**; the installed-dependency advisory audit reported **no known vulnerabilities** on 26 October 2026. The first-party package is not published on PyPI and is tested directly. Monthly Dependabot review covers uv and GitHub Actions; accepting an update still requires fresh lock/test/audit results.

| Original import | Decision | Reason |
| --- | --- | --- |
| `tkinter` | Retain; use Tkinter and ttk only | Ships with desktop CPython; no alternate GUI toolkit |
| `pyperclip` | Remove | Tkinter supplies clipboard access; avoids an unnecessary runtime package |
| `cryptography.fernet` | Retain the latest compatible `cryptography`; use Fernet for legacy recovery | Current encryption uses authenticated streaming AES-GCM plus RSA-OAEP and Argon2id from the same maintained library |
| `hashlib.sha3_512` password hashing | Replace with Argon2id | Salted, memory-hard password derivation; plain fast hashing is unsuitable for protecting passwords |
| `json` | Retain standard library | Bounded envelope and legacy parsing, rather than plaintext key storage |
| `os`, `base64` | Retain standard library | Filesystem primitives and transport encoding |
| No database | Add standard-library `sqlite3` | In-memory database serialized and encrypted as a complete image at rest |

The only direct runtime dependency is **cryptography 50.0.2** (with its resolved transitive dependencies). PyPI declares Python 3.14 support, and the locked Windows environment is validated on Python 3.14.7. The project allows compatible 50.x updates while `uv.lock` records exact versions and artifact hashes. Future upgrades require `uv lock --upgrade` and a fresh full validation run.

I chose complete-image encryption around standard-library SQLite rather than introducing a native SQLCipher binding and separate SQLite build. This supports the requested Python version and Windows workflow without storing a plaintext SQLite file. It has an explicit 64 MiB vault-size limit and rewrites the encrypted image on mutation. Large user files are streamed separately and are not embedded in the database.

Verified versions are `cryptography 50.0.2`, `pytest 9.1.1`, `ruff 0.17.2`, `pip-audit 2.10.1`, and `hatchling 1.32.4`. The exact build backend is also included in the development group so advisory checks cover it. uv manages the interpreter, environment, lockfile, runs, and build. Tk/Tcl and SQLite versions come from the Python distribution, not PyPI; the local Python 3.14.7 installation provides Tk 9.0 and SQLite 3.50.4.

Audit sources: [cryptography PyPI metadata](https://pypi.org/pypi/cryptography/json), [pyperclip PyPI metadata](https://pypi.org/pypi/pyperclip/json), [PyCA password KDF guidance](https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/), [Python SQLite documentation](https://docs.python.org/3.14/library/sqlite3.html), [uv projects](https://docs.astral.sh/uv/guides/projects/).
