"""Package an existing FluxFile Windows x64 PyInstaller build as unsigned MSIX."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
from xml.dom import minidom

from PIL import Image, ImageDraw

PACKAGING = Path(__file__).resolve().parents[1] / "packaging"
DIST = PACKAGING.parent / "dist"
LOGOS = {"StoreLogo": 50, "Square150x150Logo": 150, "Square44x44Logo": 44}


def package_version(value: str) -> str:
    if not re.fullmatch(r"[0-9]{1,5}(\.[0-9]{1,5}){3}", value):
        raise argparse.ArgumentTypeError("Use a four-part package version, such as 1.0.0.0.")
    parts = tuple(map(int, value.split(".")))
    if not 0 < parts[0] <= 65535 or any(part > 65535 for part in parts) or parts[-1] != 0:
        raise argparse.ArgumentTypeError("For Store packages, major must be 1–65535, all parts must fit in 16 bits, and the last part must be 0.")
    return ".".join(map(str, parts))


def check_windows_x64(executable: Path) -> None:
    with executable.open("rb") as binary:
        header = binary.read(64)
        if len(header) == 64 and header.startswith(b"MZ"):
            binary.seek(struct.unpack_from("<I", header, 60)[0])
            if binary.read(6) == b"PE\0\0\x64\x86":
                return
    raise ValueError(f"Expected a Windows x64 executable at {executable}")


def write_manifest(stage: Path, args: argparse.Namespace) -> None:
    with minidom.parse(str(PACKAGING / "AppxManifest.xml")) as manifest:
        identity = manifest.getElementsByTagName("Identity")[0]
        identity.setAttribute("Name", args.name)
        identity.setAttribute("Publisher", args.publisher)
        identity.setAttribute("Version", args.version)
        for tag, value in (
            ("DisplayName", args.display_name),
            ("PublisherDisplayName", args.publisher_display_name),
        ):
            manifest.getElementsByTagName("Properties")[0].getElementsByTagName(tag)[0].firstChild.data = value
        manifest.getElementsByTagName("uap:VisualElements")[0].setAttribute("DisplayName", args.display_name)
        (stage / "AppxManifest.xml").write_bytes(manifest.toxml(encoding="utf-8"))


def write_logos(stage: Path) -> None:
    assets = stage / "Assets"
    assets.mkdir()
    for name, size in LOGOS.items():
        image = Image.new("RGBA", (size, size))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 5, fill="#17222e")
        draw.line(
            [(size * x // 100, size * y // 100) for x, y in ((30, 77), (30, 25), (72, 25))],
            fill="#70e2c7",
            width=max(1, size // 10),
        )
        draw.line((size * 30 // 100, size // 2, size * 62 // 100, size // 2),
                  fill="#70e2c7", width=max(1, size // 10))
        image.save(assets / f"{name}.png")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="Package identity name from Partner Center.")
    parser.add_argument("--publisher", required=True, help="Publisher ID from Partner Center.")
    parser.add_argument("--publisher-display-name", required=True)
    parser.add_argument("--display-name", default="FluxFile")
    parser.add_argument("--version", required=True, type=package_version)
    parser.add_argument("--makeappx", type=Path, help="Path to MakeAppx.exe from the Windows SDK.")
    args = parser.parse_args()

    if sys.platform != "win32":
        parser.error("Run this command on Windows.")
    makeappx = str(args.makeappx.resolve()) if args.makeappx else shutil.which("MakeAppx.exe")
    if not makeappx:
        parser.error("Run from a Windows SDK developer prompt or supply --makeappx.")

    build = DIST / "FluxFile"
    output = DIST / f"FluxFile-{args.version}-x64.msix"
    try:
        check_windows_x64(build / "FluxFile.exe")
        if output.exists():
            raise FileExistsError(f"Package already exists: {output}")
        with TemporaryDirectory(prefix="msix-", dir=DIST) as directory:
            temp = Path(directory)
            stage = temp / "stage"
            stage.mkdir()
            shutil.copy2(build / "FluxFile.exe", stage)
            shutil.copytree(build / "_internal", stage / "_internal")
            write_manifest(stage, args)
            write_logos(stage)
            package = temp / output.name
            subprocess.run([makeappx, "pack", "/d", str(stage), "/p", str(package)], check=True)
            package.rename(output)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"MSIX packaging failed: {exc}\n")
    print(output)


if __name__ == "__main__":
    main()
