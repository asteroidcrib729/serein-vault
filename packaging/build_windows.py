"""Build unsigned x64 Windows installers from the locked project environment.

Run with: uv run --locked --group packaging python packaging/build_windows.py
Builds use isolated directories. No vault, archived binary, or credentials are bundled.
"""

import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tomllib
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

from make_assets import make_assets
from verify_release import refresh, verify_msix

ROOT = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, cwd=ROOT, **kwargs)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def sdk_tool(name):
    base = Path(os.environ["PROGRAMFILES(X86)"]) / "Windows Kits" / "10" / "bin"
    candidates = [p for p in base.glob(f"*/x64/{name}.exe") if p.parent.parent.name[0].isdigit()]
    if not candidates:
        raise RuntimeError(f"Install Windows 10/11 SDK: {name}.exe is missing.")
    return max(candidates, key=lambda p: tuple(map(int, p.parent.parent.name.split("."))))


def smoke(executable, report):
    run(executable, "--smoke-test", report, timeout=90)
    if not report.exists() or json.loads(report.read_text(encoding="utf-8")).get("ok") is not True:
        raise RuntimeError(f"Frozen application smoke check failed: {report}")


def copy_licenses(payload):
    notices = payload / "licenses"
    notices.mkdir()
    for name in ("LICENSE", "AUTHORS.md"):
        shutil.copy2(ROOT / name, payload / name)
    shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", notices / "Python-LICENSE.txt")
    for name in ("cryptography", "cffi", "pycparser", "pyinstaller"):
        dist = importlib.metadata.distribution(name)
        target = notices / name
        target.mkdir()
        for relative in dist.files or []:
            if "licenses" in relative.parts or relative.name.lower().startswith(
                ("license", "copying")
            ):
                source = Path(dist.locate_file(relative))
                if source.is_file():
                    shutil.copy2(source, target / source.name)
    # Tk 9 on Windows embeds scripts and notices in zipfs, rather than a tcl directory.
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    try:
        for name, directory in (
            ("Tcl", root.tk.call("info", "library")),
            ("Tk", root.tk.call("set", "tk_library")),
        ):
            channel = root.tk.call("open", f"{directory}/license.terms")
            try:
                content = root.tk.call("read", channel)
            finally:
                root.tk.call("close", channel)
            (notices / f"{name}-license.terms").write_text(content, encoding="utf-8")
    finally:
        root.destroy()
    (notices / "NOTICE.txt").write_text(
        "Serein Vault: Faraz Hussain and contributors, MIT.\n"
        "Bundled Python, Tcl/Tk, OpenSSL (cryptography), libffi (cffi), and PyInstaller "
        "retain their upstream license terms; see this directory and _internal data licenses.\n"
        "PyInstaller's license includes its bootloader distribution exception.\n",
        encoding="utf-8",
    )


def msix(payload, assets, destination, version):
    staging = destination.parent / "msix-staging"
    shutil.copytree(payload, staging)
    shutil.copytree(assets, staging / "Assets")
    (staging / "AppxManifest.xml").write_text(
        f'''<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
 xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
 xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
 xmlns:desktop="http://schemas.microsoft.com/appx/manifest/desktop/windows10"
 IgnorableNamespaces="uap rescap desktop">
 <Identity Name="FarazHussain.SereinVault" Publisher="CN=Faraz Hussain"
  Version="{escape(version)}.0" ProcessorArchitecture="x64"/>
 <Properties><DisplayName>Serein Vault</DisplayName>
  <PublisherDisplayName>Faraz Hussain</PublisherDisplayName>
  <Logo>Assets\\StoreLogo.png</Logo></Properties>
 <Dependencies><TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.19041.0"
  MaxVersionTested="10.0.26100.0"/></Dependencies>
 <Resources><Resource Language="en-us"/></Resources>
 <Applications><Application Id="SereinVault" Executable="SereinVault.exe"
  EntryPoint="Windows.FullTrustApplication">
  <uap:VisualElements DisplayName="Serein Vault" Description="Local encrypted files and messages"
   BackgroundColor="#121c2c" Square150x150Logo="Assets\\Square150x150Logo.png"
   Square44x44Logo="Assets\\Square44x44Logo.png"/>
 </Application></Applications>
 <Capabilities><rescap:Capability Name="runFullTrust"/></Capabilities>
</Package>''',
        encoding="utf-8",
    )
    run(sdk_tool("makeappx"), "pack", "/d", staging, "/p", destination, "/o")
    # MakeAppx validates the schema by default; verify archive identity and payload too.
    with zipfile.ZipFile(destination) as package:
        for required in ("AppxManifest.xml", "AppxBlockMap.xml", "SereinVault.exe", "LICENSE"):
            if required not in package.namelist():
                raise RuntimeError(f"MSIX is missing {required}")
        if package.testzip() is not None:
            raise RuntimeError("MSIX archive integrity failed")
    verify_msix(destination)


def provenance():
    files = {}
    for directory in ("src", "packaging", ".github", ".vscode", "development-plans", "tests"):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                files[path.relative_to(ROOT).as_posix()] = sha256(path)
    for name in (
        "pyproject.toml",
        "uv.lock",
        ".python-version",
        "README.md",
        "AUTHORS.md",
        "LICENSE",
        "main.py",
    ):
        files[name] = sha256(ROOT / name)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True))
    return {"git_head": head, "dirty_worktree": dirty, "source_sha256": files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("all", "exe", "msix"), default="all")
    parser.add_argument(
        "--inno", type=Path, help="Existing trusted ISCC.exe; otherwise verified local bootstrap"
    )
    args = parser.parse_args()
    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}:
        parser.error("Build these installers on x64 Windows.")
    if platform.python_version() != "3.14.7":
        parser.error("Use the pinned Python 3.14.7 project environment.")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    build_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    work = ROOT / ".packaging-build" / build_id
    output = ROOT / "packaged-releases" / f"{version}-{args.format}-{build_id}"
    work.mkdir(parents=True)
    output.mkdir(parents=True)
    assets = ROOT / "src" / "serein_vault" / "assets"
    if not (assets / "SereinVault.ico").exists():
        make_assets(assets)
    # Prevent unrelated Java/Git/application DLLs on PATH entering the frozen runtime.
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join(
        (
            str(Path(sys.executable).parent),
            sys.base_prefix,
            str(Path(os.environ["SYSTEMROOT"]) / "System32"),
        )
    )
    environment.pop("PYTHONPATH", None)
    run(
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name",
        "SereinVault",
        "--distpath",
        work / "dist",
        "--workpath",
        work / "build",
        "--specpath",
        work,
        "--icon",
        assets / "SereinVault.ico",
        "--manifest",
        ROOT / "packaging" / "windows.manifest",
        "--paths",
        ROOT / "src",
        "--add-data",
        f"{assets}{os.pathsep}serein_vault/assets",
        ROOT / "packaging" / "launcher.py",
        env=environment,
    )
    payload = work / "dist" / "SereinVault"
    # Every runtime DLL must have come from Python, its locked environment, or Windows.
    analysis = (work / "build" / "SereinVault" / "Analysis-00.toc").read_text(encoding="utf-8")
    allowed = [Path(p).resolve() for p in (sys.prefix, sys.base_prefix, os.environ["SYSTEMROOT"])]

    def check_dlls(node):
        if isinstance(node, (tuple, list)):
            if len(node) == 3 and node[2] == "BINARY" and isinstance(node[1], str):
                source = Path(node[1]).resolve()
                if not any(source.is_relative_to(base) for base in allowed):
                    raise RuntimeError(f"Unexpected DLL origin in frozen runtime: {source}")
            for child in node:
                check_dlls(child)

    check_dlls(ast.literal_eval(analysis))
    (output / "Analysis-00.toc").write_text(analysis, encoding="utf-8")
    copy_licenses(payload)
    smoke(payload / "SereinVault.exe", output / "frozen-smoke.json")
    if args.format in {"all", "exe"}:
        compiler = args.inno
        if compiler is None:
            tools_dir = ROOT / "packaged-releases" / ".tools"
            run(
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                ROOT / "packaging" / "bootstrap-inno.ps1",
                "-ToolsDirectory",
                tools_dir,
            )
            compiler = tools_dir / "InnoSetup" / "ISCC.exe"
        run(
            compiler.resolve(),
            f"/DAppVersion={version}",
            f"/DPayloadPath={payload}",
            f"/DOutputPath={output}",
            f"/DIconPath={assets / 'SereinVault.ico'}",
            f"/DLicensePath={ROOT / 'LICENSE'}",
            ROOT / "packaging" / "installer.iss",
        )
    if args.format in {"all", "msix"}:
        staged_msix = work / f"SereinVault-{version}-windows-x64-unsigned.msix"
        msix(payload, assets, staged_msix, version)
        shutil.copy2(staged_msix, output / staged_msix.name)
        extracted = work / "msix-extracted"
        with zipfile.ZipFile(staged_msix) as package:
            package.extractall(extracted)
        smoke(extracted / "SereinVault.exe", output / "msix-payload-smoke.json")
    shutil.copy2(ROOT / "LICENSE", output / "LICENSE")
    shutil.copy2(ROOT / "AUTHORS.md", output / "AUTHORS.md")
    evidence = provenance() | {
        "build_utc": build_id,
        "version": version,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "format": args.format,
        "pyinstaller": importlib.metadata.version("pyinstaller"),
        "signed": False,
        "msix_installation_tested": False,
        "payload_directory": str(payload.relative_to(ROOT)),
        "artifact_sha256": {
            p.name: sha256(p) for p in output.iterdir() if p.suffix in {".exe", ".msix"}
        },
    }
    (output / "provenance.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    refresh(output)
    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
            stream.write(f"release_directory={output.relative_to(ROOT).as_posix()}\n")
    print(f"Installers and evidence: {output}")


if __name__ == "__main__":
    main()
