"""Create unpublished academic previews from clean, verified installer builds."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from verify_release import verify


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_bundle(directory, source_sha, package_format):
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha) or package_format not in {"exe", "msix"}:
        raise ValueError("Use an exact source SHA and an EXE/MSIX format.")
    metadata = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
    if (
        metadata.get("git_head") != source_sha
        or metadata.get("dirty_worktree") is not False
        or metadata.get("format") != package_format
    ):
        raise ValueError("Drafts require a clean build of the requested source and format.")
    version = metadata["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid package version.")
    required = {
        "LICENSE",
        "AUTHORS.md",
        "Analysis-00.toc",
        "provenance.json",
        "frozen-smoke.json",
        "SHA256SUMS.txt",
    }
    reports = ["frozen-smoke.json"]
    if package_format == "exe":
        installer = f"SereinVault-{version}-windows-x64-setup.exe"
        reports += ["installed-smoke.json", "installer-validation.json"]
    else:
        installer = f"SereinVault-{version}-windows-x64-unsigned.msix"
        reports += ["msix-payload-smoke.json"]
    required |= {installer, *reports}
    files = sorted(directory.iterdir())
    if any(p.is_symlink() or not p.is_file() for p in files):
        raise ValueError("Release assets must be regular files without directories or links.")
    if not required.issubset({p.name for p in files}):
        raise ValueError("Required installer, licensing, provenance or smoke evidence is missing.")
    covered = [
        line.split("  ", 1)[1]
        for line in (directory / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
    ]
    if len(covered) != len(set(covered)) or set(covered) != {p.name for p in files} - {
        "SHA256SUMS.txt"
    }:
        raise ValueError("Checksum manifest must cover every asset exactly once.")
    verify(directory)
    if metadata.get("artifact_sha256") != {installer: digest(directory / installer)}:
        raise ValueError("Installer digest does not match build provenance.")
    for name in reports:
        if json.loads((directory / name).read_text(encoding="utf-8-sig")).get("ok") is not True:
            raise ValueError(f"Smoke verification did not pass: {name}")
    return version, files


class DraftPublisher:
    def __init__(self, repository, token):
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository) or not token:
            raise ValueError("A repository and scoped GitHub token are required.")
        self.repository, self.token = repository, token
        self.base = f"https://api.github.com/repos/{repository}"

    def request(self, method, url, data=None, *, binary=False):
        payload = data if binary else (json.dumps(data).encode() if data is not None else None)
        request = Request(
            url,
            data=payload,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/octet-stream" if binary else "application/json",
                "X-GitHub-Api-Version": "2026-03-10",
            },
        )
        try:
            with urlopen(request, timeout=120) as response:
                return json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f"GitHub {method} failed with HTTP {exc.code}.") from None

    def publish(self, directory, source_sha, package_format, run_id, attempt):
        version, files = validate_bundle(directory, source_sha, package_format)
        if not re.fullmatch(r"\d+", run_id) or not re.fullmatch(r"\d+", attempt):
            raise ValueError("Invalid workflow run identity.")
        tag = f"preview-{package_format}-{source_sha[:12]}-{run_id}-{attempt}"
        run_url = f"https://github.com/{self.repository}/actions/runs/{run_id}"
        body = (
            f"Academically validated Serein Vault {version} ({package_format.upper()}).\n\n"
            f"Source: {source_sha}\nBuild: {run_url}\n\n"
            "Unsigned academic preview. Review before publishing. MSIX requires a trusted "
            "signing identity before normal installation. No Store, screen-reader, or "
            "independent security certification is claimed.\n\n"
            "Installers, checksums, source provenance, MIT license, author credit, and "
            "successful smoke evidence are attached.\n\n"
            "Original author: Faraz Hussain and contributors. See AUTHORS.md and LICENSE."
        )
        release = self.request(
            "POST",
            self.base + "/releases",
            {
                "tag_name": tag,
                "target_commitish": source_sha,
                "name": f"Serein Vault {version} - {package_format.upper()} academic preview",
                "body": body,
                "draft": True,
                "prerelease": True,
                "make_latest": "false",
            },
        )
        if release.get("draft") is not True or release.get("target_commitish") != source_sha:
            raise ValueError("GitHub did not create the requested unpublished source-pinned draft.")
        release_id = int(release["id"])
        for path in files:
            url = (
                f"https://uploads.github.com/repos/{self.repository}/releases/"
                f"{release_id}/assets?name={quote(path.name, safe='')}"
            )
            asset = self.request("POST", url, path.read_bytes(), binary=True)
            if (
                asset.get("digest") != "sha256:" + digest(path)
                or asset.get("size") != path.stat().st_size
            ):
                raise ValueError(f"Uploaded asset verification failed: {path.name}")
        final = self.request("GET", self.base + f"/releases/{release_id}")
        if final.get("draft") is not True or {a["name"] for a in final["assets"]} != {
            p.name for p in files
        }:
            raise ValueError("Final draft state or asset set did not match.")
        return final["html_url"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--format", choices=("exe", "msix"), required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    url = DraftPublisher(os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"]).publish(
        args.directory,
        args.sha,
        args.format,
        os.environ["GITHUB_RUN_ID"],
        os.environ["GITHUB_RUN_ATTEMPT"],
    )
    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
            stream.write(f"release_url={url}\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as stream:
            stream.write(f"### Unpublished academic preview\n\n[Review draft release]({url})\n")
    print(url)


if __name__ == "__main__":
    main()
