"""Verify release checksums and each MSIX block against its uncompressed payload."""

import argparse
import base64
import hashlib
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


def verify_msix(path):
    with zipfile.ZipFile(path) as package:
        blockmap = ET.fromstring(package.read("AppxBlockMap.xml"))
        if blockmap.attrib["HashMethod"] != "http://www.w3.org/2001/04/xmlenc#sha256":
            raise ValueError("Unsupported MSIX block hash algorithm")
        ns = {"b": "http://schemas.microsoft.com/appx/2010/blockmap"}
        for file in blockmap.findall("b:File", ns):
            name = file.attrib["Name"].replace("\\", "/")
            content = package.read(name)
            if len(content) != int(file.attrib["Size"]):
                raise ValueError(f"MSIX size mismatch: {name}")
            blocks = file.findall("b:Block", ns)
            if len(blocks) != (len(content) + 65535) // 65536:
                raise ValueError(f"MSIX block count mismatch: {name}")
            for index, block in enumerate(blocks):
                raw = content[index * 65536 : (index + 1) * 65536]
                if hashlib.sha256(raw).digest() != base64.b64decode(block.attrib["Hash"]):
                    raise ValueError(f"MSIX block hash mismatch: {name}")
        if package.testzip() is not None:
            raise ValueError("MSIX ZIP integrity failed")


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def refresh(directory):
    files = sorted(p for p in directory.iterdir() if p.is_file() and p.name != "SHA256SUMS.txt")
    (directory / "SHA256SUMS.txt").write_text(
        "".join(f"{checksum(path)}  {path.name}\n" for path in files), encoding="utf-8"
    )


def verify(directory):
    for line in (directory / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", 1)
        path = directory / name
        if path.resolve().parent != directory.resolve() or checksum(path) != expected:
            raise ValueError(f"Release checksum mismatch: {name}")
    for path in directory.glob("*.msix"):
        verify_msix(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--refresh-checksums", action="store_true")
    args = parser.parse_args()
    if args.refresh_checksums:
        refresh(args.directory)
    verify(args.directory)
    print("Release checksums and MSIX payload blocks verified.")
