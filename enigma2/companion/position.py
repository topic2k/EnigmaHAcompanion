"""Private, access-bound receiver menu position storage."""

import hashlib
import json
import os
import tempfile

from enigmaha_protocol.menu import ID, MAX_DEPTH


class MenuPosition:
    def __init__(self, path="/etc/enigma2/enigmaha_companion_position.json"):
        self.path = path

    @staticmethod
    def identity(config):
        # Bind to the HA origin and token without storing either credential.
        value = json.dumps([config["url"].rstrip("/"), config["token"]]).encode("utf-8")
        return hashlib.sha256(value).hexdigest()

    def load(self, config):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.loads(handle.read(8193))
            if (not isinstance(data, dict) or set(data) != {"schema_version", "identity", "path"}
                    or type(data["schema_version"]) is not int or data["schema_version"] != 1
                    or data["identity"] != self.identity(config)):
                return None
            path = data["path"]
            if not isinstance(path, list) or not 1 <= len(path) <= MAX_DEPTH + 1:
                return None
            for level in path:
                if (not isinstance(level, list) or len(level) != 2
                        or not isinstance(level[0], str) or not ID.fullmatch(level[0])
                        or (level[1] is not None and
                            (not isinstance(level[1], str) or not ID.fullmatch(level[1])))):
                    return None
            return path
        except (OSError, ValueError, RecursionError):
            return None

    def save(self, config, navigator):
        directory = os.path.dirname(self.path)
        os.makedirs(directory, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".enigmaha-position-", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                os.chmod(temporary, 0o600)
                json.dump({"schema_version": 1, "identity": self.identity(config),
                           "path": navigator.position()}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
