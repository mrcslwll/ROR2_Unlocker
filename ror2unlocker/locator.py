"""
Finds Risk of Rain 2 UserProfile.xml save files, and exposes them to the
rest of the app as *profiles* (by in-game profile name) rather than as
raw file paths -- nobody should have to recognize their save by a GUID
filename.

Risk of Rain 2 is a Steam-cloud-synced game (Steam AppID 632360). Its save
profiles normally live at:

    <Steam install dir>/userdata/<your SteamID3>/632360/remote/UserProfiles/*.xml

Because "Steam install dir" varies (custom install location, a Steam
library on another drive, a fresh account with a numeric folder you don't
know, a Mac/Linux/Steam-Deck install, or a non-Steam copy), detection runs
in stages, each only attempted if the previous one came up empty:

    1. Windows registry (fast, exact).
    2. A short list of common install locations.
    3. A bounded "deep scan": every drive's top couple of directory levels,
       looking for anything with "steam" in its name that also has a
       userdata folder. This is slower but still just checks directory
       names near drive roots -- it does not walk the whole disk.

A manual "Browse..." option in the GUI always covers whatever this misses.
"""

from __future__ import annotations

import string
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

APP_ID = "632360"


@dataclass(frozen=True)
class ProfileInfo:
    """A save file, described the way a person would recognize it."""
    name: str          # in-game profile name, e.g. "Tommy"
    path: Path
    steam_id: str = ""  # the userdata/<id> folder this came from, for disambiguation

    @property
    def label(self) -> str:
        if self.steam_id:
            return f"{self.name}  (Steam account {self.steam_id})"
        return self.name


# ---------------------------------------------------------------------------
# Stage 1: registry
# ---------------------------------------------------------------------------
def _steam_paths_from_registry() -> list[Path]:
    paths = []
    if sys.platform != "win32":
        return paths
    try:
        import winreg
    except ImportError:
        return paths

    lookups = [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
    ]
    for hive, subkey, value_name in lookups:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
                if value:
                    paths.append(Path(value))
        except OSError:
            continue
    return paths


# ---------------------------------------------------------------------------
# Stage 2: common install locations
# ---------------------------------------------------------------------------
def _common_fallback_roots() -> list[Path]:
    roots = []
    if sys.platform == "win32":
        drive_letters = "CDEFGHIJ"
        program_dirs = ["Program Files (x86)/Steam", "Program Files/Steam",
                         "Steam", "SteamLibrary", "Games/Steam"]
        for letter in drive_letters:
            for sub in program_dirs:
                roots.append(Path(f"{letter}:/") / sub)
    elif sys.platform == "darwin":
        roots.append(Path.home() / "Library/Application Support/Steam")
    else:  # assume linux / steam deck
        roots.append(Path.home() / ".local/share/Steam")
        roots.append(Path.home() / ".steam/steam")
        roots.append(Path.home() / ".steam/root")
    return roots


# ---------------------------------------------------------------------------
# Stage 3: bounded deep scan (only runs if stages 1 & 2 find nothing)
# ---------------------------------------------------------------------------
def _windows_drive_roots() -> list[Path]:
    drives = []
    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:/")
        if root.exists():
            drives.append(root)
    return drives


def _deep_scan_roots() -> list[Path]:
    """
    Look near the root of every drive for anything Steam-flavored, without
    walking the whole filesystem: only the top couple of directory levels
    are inspected, and only directory *names* are matched.
    """
    if sys.platform != "win32":
        return []

    found = []
    try:
        drives = _windows_drive_roots()
    except OSError:
        return []

    for drive in drives:
        try:
            level1 = [d for d in drive.iterdir() if d.is_dir()]
        except (OSError, PermissionError):
            continue
        for d1 in level1:
            if "steam" in d1.name.lower():
                found.append(d1)
            # one more level down (e.g. D:\Games\Steam, D:\Emulation\Steam)
            try:
                for d2 in d1.iterdir():
                    if d2.is_dir() and "steam" in d2.name.lower():
                        found.append(d2)
            except (OSError, PermissionError):
                continue
    return found


# ---------------------------------------------------------------------------
# Putting it together
# ---------------------------------------------------------------------------
def _profiles_under_steam_root(root: Path, found_paths: set[Path]) -> list[Path]:
    userdata = root / "userdata"
    if not userdata.is_dir():
        return []
    results = []
    try:
        user_dirs = [d for d in userdata.iterdir() if d.is_dir()]
    except OSError:
        return []
    for user_dir in user_dirs:
        profiles_dir = user_dir / APP_ID / "remote" / "UserProfiles"
        if not profiles_dir.is_dir():
            continue
        try:
            for f in profiles_dir.glob("*.xml"):
                if ".backup_" in f.name:
                    continue  # our own backups live right next to the real profile
                if f not in found_paths:
                    found_paths.add(f)
                    results.append(f)
        except OSError:
            continue
    return results


def find_save_files(allow_deep_scan: bool = True) -> list[Path]:
    """Return every UserProfile*.xml this machine seems to have for RoR2."""
    seen: set[Path] = set()
    candidates: list[Path] = []

    for root in _steam_paths_from_registry() + _common_fallback_roots():
        candidates.extend(_profiles_under_steam_root(root, seen))

    if not candidates and allow_deep_scan:
        for root in _deep_scan_roots():
            candidates.extend(_profiles_under_steam_root(root, seen))

    return candidates


def _peek_profile_name(path: Path) -> str | None:
    """Read just enough of a save to get its <name> without fully loading it."""
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError):
        return None
    root = tree.getroot()
    if root is None or not root.tag.endswith("UserProfile"):
        return None
    name_el = root.find("name")
    if name_el is not None and name_el.text:
        return name_el.text.strip()
    return path.stem


def _steam_id_from_path(path: Path) -> str:
    # .../userdata/<steam_id>/632360/remote/UserProfiles/<file>.xml
    parts = path.parts
    try:
        idx = parts.index("userdata")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return ""


def list_profiles(allow_deep_scan: bool = True) -> list[ProfileInfo]:
    """Every save file this machine has, described by profile name."""
    profiles = []
    for path in find_save_files(allow_deep_scan=allow_deep_scan):
        name = _peek_profile_name(path)
        if name is None:
            continue
        profiles.append(ProfileInfo(name=name, path=path, steam_id=_steam_id_from_path(path)))
    return profiles


def guess_default_save() -> Path | None:
    found = find_save_files()
    return found[0] if found else None
