"""
Reads unlock data straight out of the user's installed copy of Risk of
Rain 2, so new DLC content shows up without anyone having to research or
guess its IDs.

Two sources, both plain data inside the game install:

* RoR2.dll -- every challenge is declared with an attribute like
      [RegisterAchievement("EngiBatteryDrone", "Skills.Engi.LaserCutter",
                           "Complete30StagesCareer", ...)]
  .NET stores attribute arguments as length-prefixed UTF-8 strings after a
  0x01 0x00 prolog, so the achievement -> unlock mapping can be read
  without decompiling anything.
* StreamingAssets/Language/en/*.json -- the in-game challenge names and
  descriptions ("ACHIEVEMENT_ENGIBATTERYDRONE_NAME": "Engineer: Mad
  Scientist", ...).

Running this module directly regenerates game_unlocks.py:
    python -m ror2unlocker.game_scan
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .locator import _common_fallback_roots, _steam_paths_from_registry

GAME_FOLDER = "Risk of Rain 2"
UNLOCK_PREFIX = re.compile(
    r"(Skills|Skins|Characters|Artifacts|Items|Equipment|Logs|Eclipse|NewtStatue)\."
)
_ID = re.compile(r"[A-Za-z0-9_.]+")
_PRINTABLE = re.compile(rb"^[\x20-\x7e]*$")
_LANG_PAIR = re.compile(
    r'"(ACHIEVEMENT_[A-Z0-9_]+_(?:NAME|DESCRIPTION))"\s*:\s*"((?:[^"\\]|\\.)*)"'
)


# ---------------------------------------------------------------------------
# Finding the install
# ---------------------------------------------------------------------------
def _steam_library_paths(steam_root: Path) -> list[Path]:
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    libs = [steam_root]
    try:
        text = vdf.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return libs
    for raw in re.findall(r'"path"\s+"([^"]+)"', text):
        libs.append(Path(raw.replace("\\\\", "\\")))
    return libs


def find_game_dir() -> Path | None:
    seen = set()
    for steam_root in _steam_paths_from_registry() + _common_fallback_roots():
        for lib in _steam_library_paths(steam_root):
            game = lib / "steamapps" / "common" / GAME_FOLDER
            key = str(game).lower()
            if key in seen:
                continue
            seen.add(key)
            if (game / "Risk of Rain 2_Data" / "Managed" / "RoR2.dll").is_file():
                return game
    return None


# ---------------------------------------------------------------------------
# Reading it
# ---------------------------------------------------------------------------
def _read_serstring(buf: bytes, pos: int):
    if pos >= len(buf):
        return None, pos
    n = buf[pos]
    if n == 0xFF:
        return "", pos + 1
    if n >= 0x80:
        return None, pos
    s = buf[pos + 1:pos + 1 + n]
    if len(s) != n or not _PRINTABLE.match(s):
        return None, pos
    return s.decode("ascii"), pos + 1 + n


def scan_achievement_unlocks(dll_path: Path) -> list[tuple[str, str]]:
    """[(unlock_id, achievement_id), ...] for every challenge that grants an unlock."""
    data = dll_path.read_bytes()
    found = set()
    for m in re.finditer(rb"\x01\x00", data):
        achievement, p = _read_serstring(data, m.end())
        if not achievement or not _ID.fullmatch(achievement):
            continue
        unlock, p = _read_serstring(data, p)
        if not unlock or not UNLOCK_PREFIX.match(unlock) or not _ID.fullmatch(unlock):
            continue
        prerequisite, _ = _read_serstring(data, p)
        if prerequisite is None:
            continue
        found.add((unlock, achievement))
    return sorted(found)


def load_challenge_text(language_dir: Path) -> dict[str, str]:
    text = {}
    for f in sorted(language_dir.glob("*.json")):
        try:
            raw = f.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for key, val in _LANG_PAIR.findall(raw):
            try:
                text[key] = json.loads(f'"{val}"')
            except json.JSONDecodeError:
                text[key] = val
    return text


def scan_game(game_dir: Path | None = None) -> list[tuple[str, str, str, str]]:
    """Same row shape as game_unlocks.GAME_UNLOCKS. Empty list if the game isn't found."""
    game_dir = game_dir or find_game_dir()
    if game_dir is None:
        return []
    data_dir = game_dir / "Risk of Rain 2_Data"
    pairs = scan_achievement_unlocks(data_dir / "Managed" / "RoR2.dll")
    text = load_challenge_text(data_dir / "StreamingAssets" / "Language" / "en")
    rows = []
    for unlock, achievement in pairs:
        key = achievement.upper()
        rows.append((
            unlock,
            achievement,
            text.get(f"ACHIEVEMENT_{key}_NAME", ""),
            text.get(f"ACHIEVEMENT_{key}_DESCRIPTION", ""),
        ))
    return rows


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    game = find_game_dir()
    if game is None:
        sys.exit("Risk of Rain 2 install not found.")
    rows = scan_game(game)
    print("GAME_UNLOCKS = [")
    for row in rows:
        print(f"    {row!r},")
    print("]")
    print(f"# {len(rows)} unlocks from {game}", file=sys.stderr)
