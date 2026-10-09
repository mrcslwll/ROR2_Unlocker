"""
Catalog of everything that can be unlocked in a Risk of Rain 2 save file.

Survivors, skills, skins, items and artifacts all come from
game_unlocks.GAME_UNLOCKS -- read straight out of the installed game
(RoR2.dll's achievement registrations + the game's own English challenge
text), so every ID there is exactly what the game itself writes as
<unlock>ID</unlock> when you earn it. No guessing.

On top of that, merge_game_scan() lets the app add anything an even newer
game version has introduced since that table was generated.

Logbook entries, Newt Altars and Eclipse levels aren't granted by
achievements, so they can't be read the same way; those lists still come
from a real save file plus pattern extrapolation (see their sections).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .game_unlocks import GAME_UNLOCKS


@dataclass(frozen=True)
class Unlockable:
    name: str
    unlocks: tuple
    achievement: str | None = None
    description: str = ""
    category: str = ""
    verified: bool = True


def _u(name, unlocks, achievement=None, description="", category="", verified=True):
    if isinstance(unlocks, str):
        unlocks = (unlocks,)
    return Unlockable(name, tuple(unlocks), achievement, description, category, verified)


# ---------------------------------------------------------------------------
# Display names. IDs use internal codenames ("Toolbot", "Croco", ...); these
# only affect what the checkbox says, never what gets written to the save.
# ---------------------------------------------------------------------------
SURVIVOR_DISPLAY = {
    "Commando": "Commando", "Huntress": "Huntress", "Bandit2": "Bandit",
    "Toolbot": "MUL-T", "Engi": "Engineer", "Engineer": "Engineer",
    "Mage": "Artificer", "Merc": "Mercenary", "Mercenary": "Mercenary",
    "Treebot": "REX", "Loader": "Loader", "Croco": "Acrid", "Captain": "Captain",
    "Railgunner": "Railgunner", "RailGunner": "Railgunner",
    "VoidSurvivor": "Void Fiend", "Seeker": "Seeker", "Chef": "CHEF",
    "FalseSon": "False Son", "Drifter": "Drifter", "DroneTech": "Operator",
    "Acolyte": "Acolyte", "Enforcer2": "Enforcer",
}
# Skill/skin IDs use a short code, but the matching Characters.* unlock
# sometimes spells it out.
_CHARACTER_UNLOCK_ALIASES = {"Engi": "Engineer", "Merc": "Mercenary"}

SKIN_TIERS = {
    "Alt1": "Mastery",
    "Alt2": "Prime Meridian",
    "AltSkinVulture": "Alloyed Collective (Purge)",
    "AltSkinSolus": "Alloyed Collective (Decompile)",
    "AltSkinHallow": "Hallowed Concepts (Hallow)",
    "AltSkinLynx": "Hallowed Concepts (Lynx)",
    "AltSkinFungal": "Hallowed Concepts (Fungal)",
}

ITEM_DISPLAY = {
    "AttackSpeedOnCrit": "Predatory Instincts", "AutoCastEquipment": "Gesture of the Drowned",
    "BFG": "Preon Accumulator", "Bear": "Tougher Times",
    "BossDamageBonus": "Armor-Piercing Rounds", "BounceNearby": "Sentient Meat Hook",
    "BurnNearby": "Helfire Tincture", "Cleanse": "Blast Shower", "Clover": "57 Leaf Clover",
    "Crowbar": "Crowbar", "DeathProjectile": "Forgive Me Please", "DroneBackup": "The Back-up",
    "ElementalRings": "Runald's & Kjaro's Bands", "EnergizedOnEquipmentUse": "War Horn",
    "EquipmentMagazine": "Fuel Cell", "ExecuteLowHealthElite": "Old Guillotine",
    "ExtraLife": "Dio's Best Friend", "Firework": "Bundle of Fireworks",
    "FocusConvergence": "Focused Convergence", "Gateway": "Eccentric Vase",
    "GoldGat": "The Crowdfunder", "HealAndRevive": "Seed of Life",
    "HealOnCrit": "Harvester's Scythe", "Hoof": "Paul's Goat Hoof",
    "IncreaseHealing": "Rejuvenation Rack", "Infusion": "Infusion",
    "JumpBoost": "Wax Quail", "KillEliteFrenzy": "Brainstalks",
    "Lightning": "Royal Capacitor", "LunarBadLuck": "Purity",
    "LunarSkillReplacements": "Heresy items (Visions/Hooks/Strides/Essence)",
    "Medkit": "Medkit", "Meteor": "Glowing Meteorite", "NovaOnHeal": "N'kuhana's Opinion",
    "PassiveHealing": "Gnarled Woodsprite", "Recycle": "Recycler", "Scanner": "Radar Scanner",
    "SecondarySkillMagazine": "Backup Magazine", "ShockNearby": "Unstable Tesla Coil",
    "Squid": "Squid Polyp", "Talisman": "Soulbound Catalyst", "Tonic": "Spinel Tonic",
    "TreasureCache": "Rusted Key", "WarCryOnMultiKill": "Berzerker's Pauldron",
}

ARTIFACT_DISPLAY = {
    "Bomb": "Spite", "Command": "Command", "Delusion": "Delusion", "Devotion": "Devotion",
    "EliteOnly": "Honor", "Enigma": "Enigma", "FriendlyFire": "Chaos", "Glass": "Glass",
    "MixEnemy": "Dissonance", "MonsterTeamGainsItems": "Evolution",
    "RandomSurvivorOnRespawn": "Metamorphosis", "Rebirth": "Rebirth", "Prestige": "Prestige",
    "Sacrifice": "Sacrifice", "ShadowClone": "Vengeance", "SingleMonsterType": "Kin",
    "Swarms": "Swarms", "TeamDeath": "Death", "WeakAssKnees": "Frailty", "WispOnDeath": "Soul",
}

# Hallowed Concepts (2026-10-08) additions, flagged in the list so they're
# easy to spot. Everything here is still read from the game, not guessed.
_NEW_SKILLS_HALLOWED = {
    "Skills.Engi.LaserCutter", "Skills.Commando.Sabotage", "Skills.Huntress.LaserCyclone",
    "Skills.Croco.CloyingBreath", "Skills.Mage.TectonicBlast", "Skills.Treebot.Proliferation",
}
_NEW_SURVIVORS_HALLOWED = {"Acolyte", "Enforcer2"}
_NEW_SKIN_TIERS_HALLOWED = {"AltSkinHallow", "AltSkinLynx", "AltSkinFungal"}


def _words(camel: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", camel)


def _is_new_hallowed(unlock_id: str) -> bool:
    parts = unlock_id.split(".")
    return (
        unlock_id in _NEW_SKILLS_HALLOWED
        or (len(parts) >= 2 and parts[1] in _NEW_SURVIVORS_HALLOWED)
        or (len(parts) >= 3 and parts[2] in _NEW_SKIN_TIERS_HALLOWED)
    )


def _from_row(row, detected: bool = False) -> tuple[str, Unlockable]:
    """Turn a GAME_UNLOCKS-shaped row into (category key, Unlockable)."""
    unlock_id, achievement, challenge, challenge_desc = row
    prefix, _, rest = unlock_id.partition(".")
    code, _, sub = rest.partition(".")
    survivor = SURVIVOR_DISPLAY.get(code, _words(code))

    if prefix == "Characters":
        category, name = "Survivors", survivor
    elif prefix == "Skills":
        category, name = "Skills", f"{survivor} - {_words(sub)}"
    elif prefix == "Skins":
        category, name = "Skins", f"{survivor} - {SKIN_TIERS.get(sub, _words(sub))} skin"
    elif prefix in ("Items", "Equipment"):
        category, name = "Items & Equipment", ITEM_DISPLAY.get(code, _words(code))
    elif prefix == "Artifacts":
        category, name = "Artifacts", f"Artifact of {ARTIFACT_DISPLAY.get(code, _words(code))}"
    else:
        category, name = "Other", unlock_id

    if challenge:
        name = f"{name}  [{challenge}]"
    if _is_new_hallowed(unlock_id):
        name = f"★NEW★ {name}"

    description = f"{challenge}: {challenge_desc}" if challenge else ""
    description += f"\nUnlock ID: {unlock_id}   Achievement: {achievement}"
    if detected:
        description = "Auto-detected from your installed game.\n" + description
    return category, _u(name, unlock_id, achievement, description, category.lower(), verified=True)


SURVIVORS: list[Unlockable] = []
SKILLS: list[Unlockable] = []
SKINS: list[Unlockable] = []
ITEMS: list[Unlockable] = []
ARTIFACTS: list[Unlockable] = []
OTHER: list[Unlockable] = []

_BY_CATEGORY = {
    "Survivors": SURVIVORS, "Skills": SKILLS, "Skins": SKINS,
    "Items & Equipment": ITEMS, "Artifacts": ARTIFACTS, "Other": OTHER,
}

for _row in GAME_UNLOCKS:
    _cat, _item = _from_row(_row)
    _BY_CATEGORY[_cat].append(_item)


# ---------------------------------------------------------------------------
# Logbook entries (monster / environment lore) - no achievement pairing,
# these are just discovery flags. Base-game/SotV list cross-checked against
# a second reference tool; Alloyed Collective additions confirmed straight
# from a real save. (Hallowed Concepts logs aren't covered yet -- they can't
# be read out of RoR2.dll the way achievement unlocks can.)
# ---------------------------------------------------------------------------
_MONSTER_LOG_BODIES_BASE = [
    "AltarSkeletonBody", "AncientWispBody", "ArchWispBody", "ArtifactShellBody",
    "AssassinBody", "BackupDroneBody", "BackupDroneOldBody", "BanditBody",
    "BeetleBody", "BeetleCrystalBody", "BeetleGuardAllyBody", "BeetleGuardBody",
    "BeetleGuardCrystalBody", "BeetleQueenBody", "BeetleQueen2Body", "BellBody",
    "BirdsharkBody", "BisonBody", "BomberBody", "BrotherBody", "BrotherGlassBody",
    "BrotherHauntBody", "BrotherHurtBody", "ChildBody", "ClayBody", "ClayBossBody",
    "ClayBruiserBody", "ElectricWormBody", "GolemBody", "GrandparentBody",
    "GravekeeperBody", "GreaterWispBody", "HermitCrabBody", "ImpBody", "ImpBossBody",
    "JellyfishBody", "LemurianBody", "LemurianBruiserBody", "LunarGolem",
    "LunarWisp", "MagmaWormBody", "MiniMushroom", "Nullifier", "Parent",
    "RoboBallBossBody", "RoboBallMiniBody", "Scav", "SuperRoboBallBossBody",
    "TitanBody", "TitanGoldBody", "VagrantBody", "VultureBody", "WispBody",
]
# Confirmed present verbatim (including inconsistent ".0" suffixing -- that
# inconsistency is the game's own, not a typo here) in a real Alloyed
# Collective save.
_MONSTER_LOG_BODIES_DLC = [
    ("AcidLarva", ""), ("ClayGrenadierBody", ""), ("DefectiveUnitBody", ".0"),
    ("ExtractorUnitBody", ".0"), ("FalseSonBossBody", ".0"), ("FlyingVerminBody", ".0"),
    ("GupBody", ".0"), ("HalcyoniteBody", ".0"), ("IronHaulerBody", ".0"),
    ("LunarExploder", ".0"), ("MegaConstructBody", ""), ("MiniVoidRaidCrab", ""),
    ("MinorConstructBody", ""), ("ScorchlingBody", ".0"), ("TankerBody", ".0"),
    ("VerminBody", ".0"), ("VoidBarnacleBody", ""), ("VoidInfestorBody", ""),
    ("VoidMegaCrab", ""), ("VultureHunter", ".0"), ("WorkerUnitBody", ".0"),
]
_STAGE_LOGS_BASE = [
    "arena", "artifactworld", "bazaar", "blackbeach", "dampcavesimple",
    "foggyswamp", "frozenwall", "goldshores", "golemplains", "goolake",
    "limbo", "moon", "mysteryspace", "shipgraveyard", "skymeadow", "wispgraveyard",
]
# Confirmed present verbatim in a real Alloyed Collective save.
_STAGE_LOGS_DLC_CONFIRMED = ["ancientloft", "lakes", "moon2", "solutionalhaunt"]
# Inferred, not directly confirmed as a "Logs.Stages.X" entry -- these stage
# codenames are only known because they showed up in that save's Newt Altar
# unlocks (below), so the stage log almost certainly exists but this player
# hadn't collected it yet.
_STAGE_LOGS_DLC_INFERRED = ["helminthroost", "rootjungle", "snowyforest"]

LOGS = (
    [
        _u(f"Monster Log: {body.replace('Body', '')}", f"Logs.{body}.0", None, "", "log")
        for body in _MONSTER_LOG_BODIES_BASE
    ]
    + [
        _u(f"Monster Log: {body.replace('Body', '')}", f"Logs.{body}{suffix}", None,
           "Alloyed Collective.", "log", verified=True)
        for body, suffix in _MONSTER_LOG_BODIES_DLC
    ]
    + [
        _u(f"Environment Log: {stage}", f"Logs.Stages.{stage}", None, "", "log")
        for stage in _STAGE_LOGS_BASE
    ]
    + [
        _u(f"Environment Log: {stage}", f"Logs.Stages.{stage}", None,
           "Alloyed Collective.", "log", verified=True)
        for stage in _STAGE_LOGS_DLC_CONFIRMED
    ]
    + [
        _u(f"Environment Log: {stage}", f"Logs.Stages.{stage}", None,
           "Alloyed Collective -- inferred ID, not directly confirmed.",
           "log", verified=False)
        for stage in _STAGE_LOGS_DLC_INFERRED
    ]
)

# ---------------------------------------------------------------------------
# Newt Altar / portal discoveries
# ---------------------------------------------------------------------------
# All 29 of these are confirmed verbatim from a real, heavily-played save
# (including Alloyed Collective stages: lakes, helminthroost, rootjungle,
# snowyforest). This is almost certainly not literally every Newt Altar
# location in the game -- stages this particular save hadn't found every
# altar on won't be represented -- but it is real, confirmed data rather
# than a guess.
NEWT_STATUES = [
    _u(f"Newt Altar - {loc}", f"NewtStatue.{loc}", None, "", "newt", verified=True)
    for loc in [
        "blackbeach.1", "blackbeach.2", "blackbeach2.1", "blackbeach2.2",
        "foggyswamp.0", "foggyswamp.1", "foggyswamp.2",
        "frozenwall.1", "frozenwall.2",
        "golemplains.1", "golemplains2.1", "golemplains2.2",
        "goolake.0", "goolake.1", "goolake.2",
        "helminthroost.0", "helminthroost.5",
        "lakes.0", "lakes.1",
        "rootjungle.1",
        "shipgraveyard.0", "shipgraveyard.2",
        "skymeadow.1", "skymeadow.2", "skymeadow.3", "skymeadow.4",
        "snowyforest.0",
        "wispgraveyard.0", "wispgraveyard.1",
    ]
]

# ---------------------------------------------------------------------------
# Eclipse difficulty levels (per-survivor portrait border progression,
# levels 1-8). The prefix pattern "Eclipse.<SurvivorCode>.<N>" is confirmed
# (e.g. Eclipse.Croco.2, Eclipse.Croco.3 exist in a real save) but only a
# handful of survivor/level combinations were actually observed there --
# the full 1-8 grid below is inferred by extrapolating that pattern to
# every survivor and every level, so treat entries beyond what you've
# already earned normally as unverified.
# ---------------------------------------------------------------------------
_SURVIVOR_CODES = [
    "Commando", "Huntress", "Bandit2", "Toolbot", "Engi", "Mage", "Merc",
    "Treebot", "Loader", "Croco", "Captain", "Railgunner", "VoidSurvivor",
    "Seeker", "Chef", "FalseSon", "DroneTech", "Drifter", "Acolyte", "Enforcer2",
]
_CONFIRMED_ECLIPSE = {
    ("Captain", 2), ("Croco", 2), ("Croco", 3), ("Engi", 2), ("Engi", 3),
    ("Mage", 2), ("Railgunner", 2), ("VoidSurvivor", 2),
}
ECLIPSE_LEVELS = [
    _u(f"Eclipse {level} - {SURVIVOR_DISPLAY.get(code, code)}", f"Eclipse.{code}.{level}", None,
       "Eclipse system -- ID pattern extrapolated from a real save.", "eclipse",
       verified=(code, level) in _CONFIRMED_ECLIPSE)
    for code in _SURVIVOR_CODES
    for level in range(1, 9)
]

_BY_CATEGORY.update({"Logbook": LOGS, "Newt Altars": NEWT_STATUES, "Eclipse Levels": ECLIPSE_LEVELS})

ALL_CATEGORIES = {
    "Survivors": SURVIVORS,
    "Skills": SKILLS,
    "Skins": SKINS,
    "Items & Equipment": ITEMS,
    "Artifacts": ARTIFACTS,
    "Logbook": LOGS,
    "Newt Altars": NEWT_STATUES,
    "Eclipse Levels": ECLIPSE_LEVELS,
}


def all_unlockables():
    for group in ALL_CATEGORIES.values():
        yield from group


def all_achievement_ids():
    seen = set()
    for u in all_unlockables():
        if u.achievement and u.achievement not in seen:
            seen.add(u.achievement)
            yield u.achievement


def merge_game_scan(rows) -> list[Unlockable]:
    """
    Add any unlock from a live game scan (game_scan.scan_game()) that isn't
    already in the catalog -- i.e. content newer than game_unlocks.py.
    Must run before the GUI builds its tabs. Returns what was added.
    """
    known = {u for item in all_unlockables() for u in item.unlocks}
    added = []
    for row in rows:
        if row[0] in known:
            continue
        category, item = _from_row(row, detected=True)
        _BY_CATEGORY[category].append(item)
        if category == "Other" and "Other" not in ALL_CATEGORIES:
            ALL_CATEGORIES["Other"] = OTHER
        known.add(row[0])
        added.append(item)
    return added


def required_survivor(item: Unlockable) -> Unlockable | None:
    """The Characters.* unlock a skill/skin needs to be usable, if any."""
    unlock_id = item.unlocks[0]
    prefix, _, rest = unlock_id.partition(".")
    if prefix not in ("Skills", "Skins"):
        return None
    code = rest.partition(".")[0]
    wanted = f"Characters.{_CHARACTER_UNLOCK_ALIASES.get(code, code)}"
    for survivor in SURVIVORS:
        if survivor.unlocks[0] == wanted:
            return survivor
    return None  # free survivor (Commando, Huntress, DLC-included ones, ...)
