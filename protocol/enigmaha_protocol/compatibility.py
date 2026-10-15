"""Independent release and wire-protocol identities for both components."""

import re

VERSION = "1.2.0"
PROTOCOL_VERSION = 1
PROTOCOL_HEADER = "X-EnigmaHA-Protocol"
COMPONENT_HEADER = "X-EnigmaHA-Component"
VERSION_HEADER = "X-EnigmaHA-Version"
RECEIVER_HEADER = "X-EnigmaHA-Receiver-ID"


def valid_receiver_id(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def valid_version(value):
    return (isinstance(value, str) and len(value) <= 32
            and re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", value) is not None)


def protocol_version(value, release=None):
    if value is None and release in {"1.0.0", "1.0.1", "1.0.2"}:
        # Published releases predate the header and are known to implement v1.
        return 1
    if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,4}", value):
        return int(value)
    return None


def peer_status(component, version, expected_component, protocol=None):
    if component != expected_component or not valid_version(version):
        return "unidentified_peer"
    if protocol_version(protocol, version) != PROTOCOL_VERSION:
        return "protocol_mismatch"
    return "compatible" if version == VERSION else "version_mismatch"
