# crimson-mount-repair

**A single-purpose repair utility for Crimson Desert saves affected by a mount-visibility bug introduced in patch 1.04.**

If quest-unlocked mounts — Silver Fang, Snow White Deer, Cloud Cart, Sky Streaker, and similar — disappeared from your mount menu after the 1.04 patch, this tool can detect and fix the affected records in your save file.

## What this is and what it isn't

**This is:** a single-purpose repair utility. It looks for mount records in `MercenarySaveData._mercenaryDataList` that were silently corrupted during the 1.04 save-format migration and replaces them with well-formed 1.04-schema records. It preserves each mount's `_characterKey` and `_mercenaryNo` so the record's identity is retained.

**This is not a save editor.** It cannot add items, change stats, unlock mounts you haven't earned, or modify anything outside the specific fields corrupted by the patch. The entire tool is roughly 500 lines of Python on top of ~3,300 lines of vendored parser code (see Credits). You can read it end-to-end in an hour.

**Why this exists:** the bug appears to be in Pearl Abyss's 1.04 save-migration code. A bug report has been submitted separately; the specific technical diagnosis is in [`docs/technical.md`](docs/technical.md). This tool is an interim workaround for players whose saves are currently affected.

## Requirements

- Python 3.11 or newer
- `pip install lz4 cryptography`

Windows, macOS, and Linux all work as the tool only reads and writes save files, it doesn't interact with the running game.

## Installation

```bash
git clone https://github.com/Atomic-Flip/crimson-mount-repair.git
cd crimson-mount-repair
pip install -e .
```

Or run without installing:

```bash
git clone https://github.com/Atomic-Flip/crimson-mount-repair.git
cd crimson-mount-repair/src
python -m crimson_mount_repair --help
```

## Usage

### 1. Find your save file

```bash
crimson-mount-repair list
```

On Windows this looks under `%LOCALAPPDATA%\Pearl Abyss\CD*\save\` for any `save.save` files. If you're on a different platform or your install is elsewhere, you can always pass the path explicitly.

### 2. Scan (read-only, makes no changes)

```bash
crimson-mount-repair scan
# or with an explicit path:
crimson-mount-repair scan "C:\Users\you\AppData\Local\Pearl Abyss\CD\save\<id>\slot100\save.save"
```

Expected output if your save has the bug:

```
Save: C:\Users\you\AppData\Local\Pearl Abyss\CD\save\<id>\slot100\save.save

MercenarySaveData schema: 44 fields (1.04 — supported)

Found 4 mount record(s) matching the bug signature:
  - Silver Fang                  charKey=1003918  mercNo=5573   size=207B  (no _ownedCharacterKey, no _isMainMercenary)
  - Snow White Deer              charKey=1003919  mercNo=5629   size=207B  (no _ownedCharacterKey, no _isMainMercenary)
  - Cloud Cart                   charKey=1002041  mercNo=2902   size=171B  (no _ownedCharacterKey)
  - Sky Streaker                 charKey=1002043  mercNo=3663   size=170B  (no _ownedCharacterKey, no _isMainMercenary)
```

If scan reports no broken records, your save does not have this bug and the tool has nothing to do.

### 3. Repair

```bash
crimson-mount-repair repair
```

The repair will:
1. Detect broken records using the same signature as `scan`.
2. Ask for confirmation before making any changes.
3. Write a timestamped backup of your save next to it (e.g. `save.save.backup-20260423-143055`).
4. Replace each broken record with a 1.04-schema record that preserves the mount's identity.
5. Verify the resulting save still parses cleanly before overwriting the original. If verification fails, it aborts without touching your save.

To preview without writing, use `--dry-run`. To skip the confirmation prompt (for scripting), use `--yes`.

### 4. Test in-game

Load the save in Crimson Desert and verify the repaired mounts appear in the stable mount menu. Summon each one once and save from inside the game — the game will re-serialize the records in its own canonical form, which is a more durable fix than the tool's best-effort template.

If anything goes wrong, restore the backup:

```bash
# Windows
copy "save.save.backup-20260423-143055" "save.save"

# macOS / Linux
cp "save.save.backup-20260423-143055" "save.save"
```

## Supported mounts

The tool currently recognizes these `_characterKey` values as summonable mounts:

| charKey | Name | Notes |
|---------|------|-------|
| 1003918 | Silver Fang | legendary wolf |
| 1003917 | White Bear | legendary bear |
| 1003919 | Snow White Deer | legendary deer |
| 1003912 | Rock Tusk | warthog |
| 1003915 | Icicle Edge | alpine ibex |
| 1002041 | Cloud Cart | balloon mount |
| 1002042 | Cloud Cruiser | balloon mount (added in 1.04) |
| 1002043 | Sky Streaker | balloon mount |
| 1003120 | Tiuta (Kliff's horse) | story horse |
| 1001173 | Demian's horse | story horse |
| 1001172 | Oongka's horse | story horse |
| 1000343 | Marius's horse | story horse |
| 1001984–1003564 | ATAG Mech 1–7 | mech series |

**If your missing mount isn't in this list**, please open a GitHub issue with the output of `crimson-mount-repair scan --verbose <your save>` (coming in v0.2) or the `_characterKey` of the affected mount, and we'll add it after verifying the bug signature matches.

## How it works

The 1.04 patch changed the on-disk schema of `MercenarySaveData` records, adding `_ownedCharacterKey` (u32) and `_isMainMercenary` (u8) and retaining `_lastSummoned` as an optional field. The migration code that transforms pre-1.04 records into 1.04 records has a bug that silently drops fields on certain records — specifically, records where these fields were set in the pre-1.04 save. Affected records remain in the save file but become invisible to the 1.04 mount summon menu, which appears to filter on `_ownedCharacterKey`.

This tool detects records matching the bug signature (mount charKey + missing `_ownedCharacterKey`) and replaces them in-place with a byte template taken from a verified-working 1.04 Cloud Cruiser record, with only `_characterKey` and `_mercenaryNo` rewritten per target. All other bytes — spawn position, timestamps, body-size marker, etc. — are inherited from the template and are benign initial state that the game overrides on first summon.

For the full technical diagnosis including byte-level evidence and the cross-save transition table, see [`docs/technical.md`](docs/technical.md).

## Safety

The tool will refuse to run if:

- The save's `MercenarySaveData` type table is not 44 fields (i.e., not 1.04 schema). Repairing a pre-1.04 save would produce an unreadable file.
- No broken mount records are detected. There's nothing to repair.
- The repaired save does not re-parse cleanly. Your original is preserved untouched.

The tool always writes a timestamped backup before modifying a save. Your original save is never destroyed unless you delete the backup manually.

## Credits

This tool builds on the work of the Crimson Desert community reverse-engineers. The PARC (Pearl Abyss Reflect Container) parser and save-file ChaCha20/HMAC-SHA256/LZ4 cryptography implementations are vendored from [`NattKh/CRIMSON-DESERT-SAVE-EDITOR-AND-GAME-MODS`](https://github.com/NattKh/CRIMSON-DESERT-SAVE-EDITOR-AND-GAME-MODS) (MPL-2.0), which in turn credits gek, potter4208467, LukeFZ, and fire for earlier work on the save format.

The vendored files live in `src/crimson_mount_repair/_vendor/` with their MPL-2.0 license preserved. The repair logic, detection heuristic, and CLI in the parent package are separately licensed under MIT (see `LICENSE`).

## License

MIT for this project's own code. The vendored parser files are MPL-2.0 (see `src/crimson_mount_repair/_vendor/LICENSE-MPL-2.0`).

## Disclaimer

This is an unofficial, community tool. It is not affiliated with or endorsed by Pearl Abyss. Use at your own risk. Back up your saves before using any save-modification tool, including this one (the tool makes its own backup, but your own is better).
