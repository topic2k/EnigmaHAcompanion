"""Pinned, public release assets; never send Home Assistant credentials here."""

import json
from http.client import HTTPException
import re
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .compatibility import valid_version

REPOSITORY = "topic2k/EnigmaHAcompanion"
REPOSITORY_URL = "https://github.com/" + REPOSITORY
PACKAGE = "enigma2-plugin-extensions-enigmahacompanion"
MAX_IPK_BYTES = 32 * 1024 * 1024


class UpdateError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def version_tuple(version):
    if not valid_version(version):
        raise UpdateError("invalid_release")
    return tuple(map(int, version.split(".")))


def asset_url(version, name):
    version_tuple(version)
    return REPOSITORY_URL + "/releases/download/v" + version + "/" + name


def ipk_name(version):
    version_tuple(version)
    return PACKAGE + "_" + version + "_all.ipk"


def validate_release(value):
    if not isinstance(value, dict) or set(value) != {"version", "ipk_url", "ipk_sha256", "ipk_size"}:
        raise UpdateError("invalid_release")
    version = value["version"]
    version_tuple(version)
    if (value["ipk_url"] != asset_url(version, ipk_name(version))
            or not isinstance(value["ipk_sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", value["ipk_sha256"]) is None
            or type(value["ipk_size"]) is not int or not 0 < value["ipk_size"] <= MAX_IPK_BYTES):
        raise UpdateError("invalid_release")
    return dict(value)


def release_metadata(value):
    if (not isinstance(value, dict) or value.get("draft") is not False
            or value.get("prerelease") is not False):
        raise UpdateError("invalid_release")
    tag = value.get("tag_name")
    if not isinstance(tag, str) or not tag.startswith("v"):
        raise UpdateError("invalid_release")
    version = tag[1:]
    version_tuple(version)
    assets = value.get("assets")
    if not isinstance(assets, list):
        raise UpdateError("invalid_release")
    required = (ipk_name(version), "enigmaha_companion.zip", "SHA256SUMS.txt")
    selected = {}
    for name in required:
        matches = [asset for asset in assets if isinstance(asset, dict) and asset.get("name") == name]
        if len(matches) != 1 or matches[0].get("browser_download_url") != asset_url(version, name):
            raise UpdateError("invalid_release")
        selected[name] = matches[0]
    return version, selected


def release_with_checksums(metadata, checksum_text):
    version, assets = release_metadata(metadata)
    sums = {}
    for line in checksum_text.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        if not match or match[2] in sums:
            raise UpdateError("invalid_release")
        sums[match[2]] = match[1]
    name = ipk_name(version)
    if name not in sums or "enigmaha_companion.zip" not in sums:
        raise UpdateError("invalid_release")
    return validate_release({"version": version, "ipk_url": asset_url(version, name),
                             "ipk_sha256": sums[name], "ipk_size": assets[name].get("size")})


def _public_url(url):
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443)
            or parts.hostname not in {"api.github.com", "github.com", "release-assets.githubusercontent.com",
                                      "objects.githubusercontent.com"}):
        raise UpdateError("download_failed")


class _PublicRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_public(url):
    _public_url(url)
    return build_opener(_PublicRedirect()).open(Request(url, headers={
        "User-Agent": "EnigmaHACompanion", "Accept": "application/vnd.github+json"
        if urlsplit(url).hostname == "api.github.com" else "application/octet-stream",
    }), timeout=20)


def _read_public(url, limit):
    with open_public(url) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise UpdateError("download_failed")
    return data


def fetch_latest_release():
    try:
        metadata = json.loads(_read_public("https://api.github.com/repos/" + REPOSITORY + "/releases/latest", 1024 * 1024))
        version, _ = release_metadata(metadata)
        checksums = _read_public(asset_url(version, "SHA256SUMS.txt"), 128 * 1024).decode("ascii")
        return release_with_checksums(metadata, checksums)
    except UpdateError:
        raise
    except (OSError, ValueError, UnicodeError, HTTPException, RecursionError):
        raise UpdateError("release_check_failed") from None
