# ROR2 Unlocker™ — Totally Legit Save Editor (2003 Edition)

A save file editor for **Risk of Rain 2**. Unlocks survivors, alternate
skills, skins, items/equipment, artifacts, logbook entries, and Newt Altar
portals, plus lets you set Lunar Coins — all in a deliberately, ironically
retro Comic-Sans, beveled-gray-Windows GUI with a hand-drawn "lunar bazaar"
backdrop.

> ⚠️ This edits a local save file only. Nothing is uploaded anywhere. It
> creates a timestamped backup next to your save every time you save.
> Close Risk of Rain 2 before editing, and don't relaunch it until you're
> done, or Steam Cloud may overwrite your edits.

## Running from source

Requires Python 3.10+ (uses only the standard library — no pip installs
needed to run it):

```bash
python main.py
```

## How it works

Risk of Rain 2 stores your progress in a plain XML file:

```
<Steam install dir>\userdata\<your SteamID3>\632360\remote\UserProfiles\<random>.xml
```

You never have to deal with that filename. The app looks in three stages,
each only tried if the last one found nothing:

1. Windows registry (exact, fast).
2. A short list of common Steam install locations (other drive letters,
   `SteamLibrary`, etc.).
3. A bounded scan of every drive's top couple of directory levels for
   anything with "steam" in its name -- for the odd installs the first
   two stages miss, without walking your whole disk.

Every save file found is opened just enough to read its in-game **profile
name** (e.g. "Commando Main"), and that's what shows up in the
**Profile** dropdown on the General tab -- pick a profile by name, not a
GUID filename. Hit **Rescan** to re-run detection (handy right after
installing to a new drive), or **Browse for a file...** for anything
detection still can't find (synced from elsewhere, a manual backup copy,
non-Steam install, etc.) -- browsed files are added to the dropdown too.

Unlocks are written as `<unlock>Category.Id</unlock>` entries alongside
the matching achievement, exactly like the game itself would write them
when you earn something legitimately.

**Lunar Coins** are stored in `<coins>` as a plain C# 32-bit signed integer
(`int`) -- confirmed both by community reports of the counter going
negative past ~2.1 billion, and directly from a dedicated third-party
Lunar Coins editor whose `LunarCoins` field is typed `int` and maxes out
at `int.MaxValue`. So **2,147,483,647** is the real ceiling the save
format can hold at all, not a number this app made up; entering more (or
less than 0) gets clamped to fit.

**Save As New Profile** writes everything you've staged in memory out to
a brand-new save file (fresh filename, same `UserProfiles` folder RoR2
itself uses by default) instead of overwriting the one you loaded.

> ⚠️ **Known limitation, confirmed by testing:** Risk of Rain 2 does not
> build its profile-selection list by scanning the `UserProfiles` folder.
> It reads Steam Cloud's own manifest for the app --
> `userdata\<id>\632360\remotecache.vdf`, a small text file listing every
> file Steam Cloud actually knows about, by exact relative path, size and
> hash. A file this app (or any external tool) writes directly to disk is
> never added to that manifest, so **the game will not offer a
> Save-As-created file as a profile to load, no matter what it's named or
> how long you wait** -- confirmed by creating one, launching the game,
> and finding it absent from both the in-game list and `remotecache.vdf`
> afterward, even though the file itself was perfectly valid XML.
>
> Two things do reliably work instead:
> - **Edit an existing profile in place** (Save Changes to File). It's
>   already in the Cloud manifest, so the game always sees the edit; the
>   automatic backup keeps it reversible.
> - **Workaround for a real "second save file":** create a new, empty
>   profile from *inside* Risk of Rain 2 itself first (its own "New
>   Profile" flow presumably registers the file with Steam Cloud properly)
>   -- then close the game, hit **Rescan** in this app, pick that
>   freshly-created profile from the dropdown, and unlock whatever you
>   want into it with Save Changes to File. This hasn't been verified end
>   to end yet; if you try it, let me know whether it works.

## A note on DLC coverage

**Survivors, skills, skins, items and artifacts are read straight out of
the game, not researched or guessed.** Every challenge in Risk of Rain 2
is declared in `RoR2.dll` with an attribute like

```
[RegisterAchievement("EngiBatteryDrone", "Skills.Engi.LaserCutter", "Complete30StagesCareer", ...)]
```

-- achievement ID, the exact `<unlock>` it grants, and its prerequisite.
.NET stores those arguments as plain length-prefixed UTF-8, so
`ror2unlocker/game_scan.py` can read them without decompiling anything,
then joins them with the game's own English challenge text from
`StreamingAssets/Language/en/*.json`.

- `ror2unlocker/game_unlocks.py` is that table, generated from the
  Hallowed Concepts build (Steam build 25475991, 2026-10-08): 205 unlocks,
  each with its real challenge name and description.
- **On every launch the app re-scans your installed game** (~0.3s) and
  adds anything newer than that table, so the next DLC shows up on its own
  -- no research, no guessing. The Activity Log says what it found.
- Regenerate the table by hand with `python -m ror2unlocker.game_scan`.

New Hallowed Concepts content is marked **★NEW★** in the lists. Hover any
entry to see its in-game challenge and raw unlock ID. Picking a skill or
skin for a survivor you haven't unlocked unlocks that survivor too.

Example -- Engineer's new primary, **Laser Cutter**:
`Skills.Engi.LaserCutter`, granted by `EngiBatteryDrone` ("Engineer: Mad
Scientist -- As Engineer, repair an Equipment Drone with an Escape Pod's
Fuel Array.").

Logbook entries, Newt Altars and Eclipse levels aren't granted by
achievements, so they can't be read this way. Those still come from a real
save plus pattern extrapolation; extrapolated ones are marked
**⚠ unconfirmed** (hover for details).

### The 🧪 DLC Lab tab

Every remaining unconfirmed entry (Eclipse levels and a few stage logs),
gathered in one place with a note on what's confirmed vs. extrapolated.
**Apply All Experimental Guesses to Current
Profile** unlocks everything (including the guesses) directly onto
whichever profile is loaded in the dropdown above -- deliberately *not* a
new file, per the Save-As limitation above, so the game actually picks it
up. A backup is made automatically first. Click ✅/❌ per item after
checking in-game -- it writes a verdict line to the Activity Log, which
you can copy straight back into chat so the catalog gets corrected.

## Building the standalone .exe

Already built once -- `dist/ROR2 Unlocker.exe` exists and runs standalone
(confirmed: launches, auto-detects and loads a real profile, no errors).
To rebuild after changing the code:

```bash
pip install -r requirements.txt
pyinstaller "ROR2 Unlocker.spec"
```

(`ROR2 Unlocker.spec` was generated by the first build and records the
exact settings -- one-file, windowed, `assets/icon.ico` as both the exe's
icon and a bundled data file the app reads at runtime for the window's own
icon. To build completely from scratch instead: `pyinstaller --onefile
--windowed --name "ROR2 Unlocker" --icon assets/icon.ico --add-data
"assets/icon.ico;assets" main.py` -- regenerate the icon first with `python
make_icon.py` if `assets/icon.ico` is missing.)

The finished executable has no external dependencies at runtime (the
lunar-bazaar background is drawn in code, not loaded from an image file),
so it's safe to hand the single ~11 MB .exe to someone else -- `build/` is
just PyInstaller's intermediate cache and isn't needed to run it.

## Data source / disclaimer

The unlock-ID catalog (`ror2unlocker/data.py`) was reconstructed from a
real exported save file and cross-checked against the unlock table used
by an existing open-source community save editor. No game assets, code,
or copyrighted artwork are bundled with this project — the GUI background
is procedurally drawn.
