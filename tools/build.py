"""Build standalone HA ZIP and Enigma2 IPK/tar.gz (stdlib only)."""

import argparse
import ast
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]


def copy_python_tree(source, target, rewrite=False):
    for file in source.rglob("*"):
        if not file.is_file() or "__pycache__" in file.parts or file.suffix == ".pyc":
            continue
        dest = target / file.relative_to(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if rewrite and file.suffix == ".py":
            dest.write_text(file.read_text(encoding="utf-8").replace(
                "from enigmaha_protocol", "from ..enigmaha_protocol"), encoding="utf-8")
        else:
            shutil.copyfile(file, dest)


def tar_bytes(files):
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, data, mode in files:
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), mode, 0
            info.uid = info.gid = 0
            archive.addfile(info, io.BytesIO(data))
    return gzip.compress(result.getvalue(), mtime=0)


def ar_bytes(members):
    result = bytearray(b"!<arch>\n")
    for name, data in members:
        header = "{:<16}{:<12}{:<6}{:<6}{:<8}{:<10}`\n".format(name + "/", 0, 0, 0, "100644", len(data))
        result.extend(header.encode("ascii"))
        result.extend(data)
        if len(data) % 2:
            result.extend(b"\n")
    return bytes(result)


def build(output):
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", VERSION):
        raise ValueError("package version must use MAJOR.MINOR.PATCH")
    source = ROOT / "custom_components/enigmaha_companion"
    manifest_version = json.loads((source / "manifest.json").read_text(encoding="utf-8"))["version"]
    constants = ast.parse((source / "const.py").read_text(encoding="utf-8"))
    panel_version = next(ast.literal_eval(node.value) for node in constants.body
                         if isinstance(node, ast.Assign)
                         and any(isinstance(target, ast.Name) and target.id == "VERSION" for target in node.targets))
    if manifest_version != VERSION or panel_version != VERSION:
        raise ValueError("package.json, HA manifest and panel version must match")
    peer_constants = ast.parse((ROOT / "protocol/enigmaha_protocol/compatibility.py").read_text(encoding="utf-8"))
    peer_version = next(ast.literal_eval(node.value) for node in peer_constants.body
                        if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == "VERSION" for target in node.targets))
    if peer_version != VERSION:
        raise ValueError("receiver/HA compatibility version must match the package version")
    output = output.resolve()
    if output != (ROOT / "dist").resolve():
        raise ValueError("build output must be the project's dist directory")
    output.mkdir(parents=True, exist_ok=True)
    bundle = output / "unpacked"
    # A dedicated generated directory; never delete arbitrary caller paths.
    if bundle.exists():
        if bundle.resolve().parent != output or bundle.is_symlink():
            raise ValueError("refusing redirected build directory")
        shutil.rmtree(bundle)
    ha = bundle / "homeassistant" / "custom_components" / "enigmaha_companion"
    receiver = bundle / "enigma2" / "usr/lib/enigma2/python/Plugins/Extensions/EnigmaHACompanion"
    copy_python_tree(source, ha)
    copy_python_tree(ROOT / "protocol/enigmaha_protocol", ha / "enigmaha_protocol")
    copy_python_tree(ROOT / "enigma2/Plugins/Extensions/EnigmaHACompanion", receiver)
    copy_python_tree(ROOT / "enigma2/companion", receiver / "companion", rewrite=True)
    copy_python_tree(ROOT / "protocol/enigmaha_protocol", receiver / "enigmaha_protocol")

    ha_zip = output / ("enigmaha-companion-ha-" + VERSION + ".zip")
    with zipfile.ZipFile(ha_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted((bundle / "homeassistant").rglob("*")):
            if file.is_file():
                archive.write(file, file.relative_to(bundle / "homeassistant").as_posix())
    # HACS extracts release ZIPs directly into custom_components/<domain>.
    # Unlike the manual-install ZIP, this archive must not have a folder prefix.
    hacs_manifest = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
    hacs_zip = output / hacs_manifest["filename"]
    if hacs_zip.parent != output or hacs_zip.suffix != ".zip" or hacs_zip == ha_zip:
        raise ValueError("HACS filename must be a distinct ZIP filename without directories")
    with zipfile.ZipFile(hacs_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(ha.rglob("*")):
            if file.is_file():
                archive.write(file, file.relative_to(ha).as_posix())
    files = [(file.relative_to(bundle / "enigma2").as_posix(), file.read_bytes(), 0o644)
             for file in sorted(receiver.rglob("*")) if file.is_file()]
    data = tar_bytes(files)
    receiver_tar = output / ("enigmaha-companion-enigma2-" + VERSION + ".tar.gz")
    receiver_tar.write_bytes(data)
    # OpenEmbedded splits urllib/http into netclient and ssl/_ssl/tempfile into io.
    # Python module names are not necessarily installable package names.
    control = ("Package: enigma2-plugin-extensions-enigmahacompanion\nVersion: " + VERSION + "\n"
               "Architecture: all\nMaintainer: EnigmaHA Companion contributors\n"
               "Section: extra\nPriority: optional\n"
               "Depends: enigma2, python3-core (>= 3.13), python3-json, python3-netclient, python3-io, python3-twisted-core\n"
               "Description: Home Assistant text menu for Enigma2 receivers\n")
    ipk = ar_bytes([("debian-binary", b"2.0\n"),
                    ("control.tar.gz", tar_bytes([("control", control.encode(), 0o644)])),
                    ("data.tar.gz", data)])
    receiver_ipk = output / ("enigma2-plugin-extensions-enigmahacompanion_" + VERSION + "_all.ipk")
    receiver_ipk.write_bytes(ipk)
    # Ignore packages left by earlier builds; never publish stale versions.
    deliverables = sorted([ha_zip, hacs_zip, receiver_tar, receiver_ipk])
    (output / "SHA256SUMS.txt").write_text("".join(
        hashlib.sha256(file.read_bytes()).hexdigest() + "  " + file.name + "\n" for file in deliverables), encoding="ascii")
    print(json.dumps({"version": VERSION, "packages": [file.name for file in deliverables]}))
    return bundle


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    # Resolve before any directory cleanup; the generated tree must be local to
    # this project's dedicated dist directory.
    destination = args.output.resolve()
    if destination != (ROOT / "dist").resolve():
        parser.error("output must be this project's dist directory")
    build(destination)
