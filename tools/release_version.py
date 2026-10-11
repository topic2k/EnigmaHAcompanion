"""Select a release version and synchronize project metadata (stdlib only)."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILES = (
    "package.json",
    "package-lock.json",
    "custom_components/enigmaha_companion/manifest.json",
    "custom_components/enigmaha_companion/const.py",
    "protocol/enigmaha_protocol/compatibility.py",
)
SEMVER = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"


def parse_version(value):
    if not re.fullmatch(SEMVER, value):
        raise ValueError("Version must use MAJOR.MINOR.PATCH without a v prefix or suffix")
    return tuple(map(int, value.split(".")))


def select_version(current, tags, bump="patch", explicit=""):
    current = parse_version(current)
    released = [parse_version(tag[1:]) for tag in tags
                if re.fullmatch("v" + SEMVER, tag)]
    if explicit.strip():
        chosen = parse_version(explicit.strip())
        if chosen < current or any(chosen <= version for version in released):
            raise ValueError("Explicit version must be at least the project version and newer than all release tags")
    else:
        baseline = max([current] + released)
        index = {"major": 0, "minor": 1, "patch": 2}[bump]
        chosen = baseline[:index] + (baseline[index] + 1,) + (0,) * (2 - index)
    return ".".join(map(str, chosen))


def update_versions(root, version):
    parse_version(version)
    replacements = {}
    for filename in VERSION_FILES[:3]:
        path = root / filename
        content = json.loads(path.read_text(encoding="utf-8"))
        content["version"] = version
        if filename == "package-lock.json":
            content["packages"][""]["version"] = version
        replacements[path] = json.dumps(content, indent=2, ensure_ascii=False) + "\n"
    for filename in VERSION_FILES[3:]:
        path = root / filename
        constants, count = re.subn(r'^VERSION = "[^"]+"$', f'VERSION = "{version}"',
                                   path.read_text(encoding="utf-8"), flags=re.MULTILINE)
        if count != 1:
            raise ValueError("Expected exactly one VERSION assignment in " + filename)
        replacements[path] = constants
    # Prepare and validate all files before changing any of them.
    for path, content in replacements.items():
        path.write_text(content, encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bump", choices=("major", "minor", "patch"), default="patch")
    parser.add_argument("--version", default="")
    args = parser.parse_args()
    try:
        current = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
        tags = subprocess.check_output(["git", "tag", "--list", "v*"], cwd=ROOT, text=True).splitlines()
        version = select_version(current, tags, args.bump, args.version)
        update_versions(ROOT, version)
    except ValueError as error:
        parser.error(str(error))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(f"version={version}\n")
    print(f"Release version: {version}")


if __name__ == "__main__":
    main()
