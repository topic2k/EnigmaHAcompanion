"""Register a profile once to expose it to detection, settings and validation."""

from .GradientFHD import GradientProfile
from .native import NativeProfile

PROFILES = (NativeProfile(), GradientProfile())


def profile_choices():
    return [("auto", "Automatisch")] + [(profile.id, profile.label) for profile in PROFILES]


def resolve_profile(selection, skin_path=""):
    if selection != "auto":
        for profile in PROFILES:
            if profile.id == selection:
                return profile
        raise ValueError("Unbekanntes Skin-Profil")
    directories = skin_path.replace("\\", "/").casefold().split("/")[:-1]
    for profile in PROFILES:
        if any(name.casefold() in directories for name in profile.skin_directories):
            return profile
    return next(profile for profile in PROFILES if profile.id == "native")
