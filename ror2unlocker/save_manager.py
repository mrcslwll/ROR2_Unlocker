"""
Reads, edits, and writes a Risk of Rain 2 UserProfile.xml save file.

File shape (confirmed against a real exported profile):

    <UserProfile>
        <coins>72</coins>
        <achievementsList>KillEliteMonster CompleteTeleporter ...</achievementsList>
        <stats>
            <stat name="totalKills">67765</stat>
            ...
            <unlock>Items.Medkit</unlock>
            <unlock>Characters.Mercenary</unlock>
            ...
        </stats>
        ...
    </UserProfile>

Unlocks (survivors, items, skills, skins, artifacts, logbook entries, newt
altars) are recorded as bare ``<unlock>ID</unlock>`` elements living
*inside* ``<stats>``, interleaved with the ``<stat>`` entries -- that is
how the game itself writes them, so this module writes them the same way.
"""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from .data import Unlockable

UNLOCK_TAG = "unlock"
STATS_TAG = "stats"
COINS_TAG = "coins"
ACHIEVEMENTS_TAG = "achievementsList"
NAME_TAG = "name"

# The <coins> field is serialized straight from a C# `int` (confirmed both
# by the community-reported "goes negative past ~2.1 billion" overflow bug,
# and directly by a dedicated Lunar Coins editor tool whose LunarCoins
# property is typed `int` and defaults to `int.MaxValue`). That makes
# Int32.MaxValue the hard ceiling this save format can represent at all --
# anything above it either doesn't fit or wraps around to negative.
LUNAR_COINS_MAX = 2_147_483_647


class SaveFileError(Exception):
    pass


class SaveFile:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.tree: ET.ElementTree | None = None
        self.root: ET.Element | None = None
        self.load()

    # -- loading -----------------------------------------------------
    def load(self) -> None:
        try:
            self.tree = ET.parse(self.path)
        except ET.ParseError as exc:
            raise SaveFileError(f"This doesn't look like a valid save file: {exc}") from exc
        self.root = self.tree.getroot()
        if self.root is None or not self.root.tag.endswith("UserProfile"):
            raise SaveFileError("This XML file doesn't look like a RoR2 UserProfile save.")

    def _stats(self) -> ET.Element:
        stats = self.root.find(STATS_TAG)
        if stats is None:
            stats = ET.SubElement(self.root, STATS_TAG)
        return stats

    # -- profile name / basic info ------------------------------------
    @property
    def profile_name(self) -> str:
        el = self.root.find(NAME_TAG)
        return el.text if el is not None and el.text else "(unnamed)"

    def set_profile_name(self, name: str) -> None:
        el = self.root.find(NAME_TAG)
        if el is None:
            el = ET.SubElement(self.root, NAME_TAG)
        el.text = name

    # -- lunar coins ---------------------------------------------------
    def get_coins(self) -> int:
        el = self.root.find(COINS_TAG)
        if el is None or not el.text:
            return 0
        try:
            return int(el.text.strip())
        except ValueError:
            return 0

    def set_coins(self, value: int) -> None:
        el = self.root.find(COINS_TAG)
        if el is None:
            el = ET.SubElement(self.root, COINS_TAG)
        clamped = max(0, min(int(value), LUNAR_COINS_MAX))
        el.text = str(clamped)

    # -- achievements ----------------------------------------------------
    def _achievements_element(self) -> ET.Element:
        el = self.root.find(ACHIEVEMENTS_TAG)
        if el is None:
            el = ET.SubElement(self.root, ACHIEVEMENTS_TAG)
            el.text = ""
        return el

    def get_achievements(self) -> set[str]:
        el = self._achievements_element()
        text = (el.text or "").strip()
        return set(text.split()) if text else set()

    def add_achievement(self, achievement_id: str) -> None:
        if not achievement_id:
            return
        current = self.get_achievements()
        if achievement_id in current:
            return
        current.add(achievement_id)
        el = self._achievements_element()
        el.text = " ".join(sorted(current))

    def remove_achievement(self, achievement_id: str) -> None:
        current = self.get_achievements()
        if achievement_id not in current:
            return
        current.discard(achievement_id)
        el = self._achievements_element()
        el.text = " ".join(sorted(current))

    # -- unlocks -----------------------------------------------------
    def get_unlocks(self) -> set[str]:
        stats = self._stats()
        return {
            (el.text or "").strip()
            for el in stats.findall(UNLOCK_TAG)
            if el.text and el.text.strip()
        }

    def has_unlock(self, unlock_id: str) -> bool:
        return unlock_id in self.get_unlocks()

    def add_unlock(self, unlock_id: str) -> None:
        if self.has_unlock(unlock_id):
            return
        stats = self._stats()
        el = ET.SubElement(stats, UNLOCK_TAG)
        el.text = unlock_id

    def remove_unlock(self, unlock_id: str) -> None:
        stats = self._stats()
        for el in list(stats.findall(UNLOCK_TAG)):
            if (el.text or "").strip() == unlock_id:
                stats.remove(el)

    # -- high level helpers --------------------------------------------
    def apply_unlockable(self, item: Unlockable, grant_achievement: bool = True) -> None:
        for unlock_id in item.unlocks:
            self.add_unlock(unlock_id)
        if grant_achievement and item.achievement:
            self.add_achievement(item.achievement)

    def revoke_unlockable(self, item: Unlockable) -> None:
        for unlock_id in item.unlocks:
            self.remove_unlock(unlock_id)
        if item.achievement:
            self.remove_achievement(item.achievement)

    def is_unlockable_granted(self, item: Unlockable) -> bool:
        return all(self.has_unlock(u) for u in item.unlocks)

    # -- saving / backup --------------------------------------------------
    def backup_path(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.path.with_name(f"{self.path.stem}.backup_{stamp}{self.path.suffix}")

    def make_backup(self) -> Path:
        backup = self.backup_path()
        shutil.copy2(self.path, backup)
        return backup

    def save(self, make_backup: bool = True) -> Path | None:
        backup_made = None
        if make_backup and self.path.exists():
            backup_made = self.make_backup()

        # ElementTree escapes text/attributes itself; RoR2's own parser
        # doesn't care about pretty-printing so we write compactly, same
        # as the game does.
        self.tree.write(self.path, encoding="UTF-8", xml_declaration=True)
        return backup_made

    def save_as(self, new_path: Path) -> None:
        """
        Write the current (edited) in-memory save out to a brand-new file,
        leaving whatever this object's own .path points at completely
        untouched. Does not repoint self.path -- callers that want the app
        to keep editing the new file should open it as a fresh SaveFile.
        """
        new_path = Path(new_path)
        new_path.parent.mkdir(parents=True, exist_ok=True)
        self.tree.write(new_path, encoding="UTF-8", xml_declaration=True)
