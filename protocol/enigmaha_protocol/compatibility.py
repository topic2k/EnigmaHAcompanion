"""Release identity exchanged by the HA integration and receiver plugin."""

import re

VERSION = "1.0.2"
COMPONENT_HEADER = "X-EnigmaHA-Component"
VERSION_HEADER = "X-EnigmaHA-Version"
RECEIVER_HEADER = "X-EnigmaHA-Receiver-ID"


def valid_receiver_id(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def valid_version(value):
    return (isinstance(value, str) and len(value) <= 32
            and re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", value) is not None)


def peer_status(component, version, expected_component):
    if component != expected_component or not valid_version(version):
        return "unidentified_peer"
    return "compatible" if version == VERSION else "version_mismatch"
