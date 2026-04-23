# SPDX-License-Identifier: MIT
"""Known summonable-mount character keys in Crimson Desert.

This list is used to decide whether a given MercenarySaveData record in a
save file corresponds to a player-summonable mount. Only records whose
_characterKey is in this list are candidates for repair.

Seeded from NattKh's MOUNT_TEMPLATES dict (https://github.com/NattKh/...),
trimmed to mounts that are player-summonable via the stable menu and
reported (or plausibly) affected by the 1.04 migration bug.

If your missing mount isn't in this list, open a GitHub issue with the
output of `crimson-mount-repair --scan --verbose` on your save and we'll
consider adding it.
"""
from __future__ import annotations

# charKey -> (display name, notes)
SUMMONABLE_MOUNTS: dict[int, tuple[str, str]] = {
    # Legendary wild mounts (quest/exploration unlocks)
    1003918: ("Silver Fang", "legendary wolf"),
    1003917: ("White Bear", "legendary bear"),
    1003919: ("Snow White Deer", "legendary deer"),
    1003912: ("Rock Tusk", "warthog"),
    1003915: ("Icicle Edge", "alpine ibex"),
    # Story/mission-unlocked special mounts
    1002041: ("Cloud Cart", "balloon mount"),
    1002042: ("Cloud Cruiser", "balloon mount (1.04 addition)"),
    1002043: ("Sky Streaker", "balloon mount"),
    # Named-character mounts
    1003120: ("Tiuta (Kliff's horse)", "story horse"),
    1001173: ("Demian's horse", "story horse"),
    1001172: ("Oongka's horse", "story horse"),
    1000343: ("Marius's horse", "story horse"),
    # ATAG mech series
    1001984: ("ATAG Mech 1", "mech"),
    1001985: ("ATAG Mech 2", "mech"),
    1001986: ("ATAG Mech 3", "mech"),
    1000017: ("ATAG Mech 4", "mech"),
    1003562: ("ATAG Mech 5", "mech"),
    1003563: ("ATAG Mech 6", "mech"),
    1003564: ("ATAG Mech 7", "mech"),
}


def is_summonable_mount(char_key: int) -> bool:
    """Return True if char_key corresponds to a summonable mount."""
    return char_key in SUMMONABLE_MOUNTS


def mount_name(char_key: int) -> str:
    """Return a human-readable name for a mount charKey, or a fallback."""
    if char_key in SUMMONABLE_MOUNTS:
        return SUMMONABLE_MOUNTS[char_key][0]
    return f"Unknown mount (charKey={char_key})"
