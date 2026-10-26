# Deprecated EncryptZone artifacts

The current replacement is [Serein Vault](../README.md), an academically validated desktop application. Current build/draft workflows package supported source and exclude this archive. See [academic readiness](../development-plans/ACADEMIC-READINESS.md).

These files are archived historical coursework materials. They are **not supported**, installed, or imported by Serein Vault.

| Artifact | Status | Original SHA-256 |
| --- | --- | --- |
| `main.py.exe.deprecated` | Old executable; renamed to prevent ordinary `.exe` launch | `529ea7de631f7d67afeada18eb5dbb8116876362b3530ec6b05f8510ab4b5c02` |
| `Project Report.pdf` | Old academic report; superseded by the root README and `development-plans/` | `464e358738b27a2bb3339b6546e85181b208bc21a3441d5128d23f4faf66c18c` |
| `main.py.txt` | Reference copy of the old source; contains known vulnerabilities | See Git history for the original source |

The executable and report are preserved byte-for-byte. Do not rename or run the old executable for current use. Its bundled libraries have not been inventoried or endorsed. The prototype's tracked plaintext password-hash file was removed from the active tree; import surviving credentials and keys only through the new encrypted vault workflow.
