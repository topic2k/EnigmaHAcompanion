"""Dependency-free EnigmaHA Companion protocol v1 (Python 3.8+)."""

from .menu import ProtocolError, validate_menu
from .actions import ActionError, prepare_action

__all__ = ["ProtocolError", "validate_menu", "ActionError", "prepare_action"]
