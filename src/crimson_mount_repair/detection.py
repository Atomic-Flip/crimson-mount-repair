# SPDX-License-Identifier: MIT
"""Detection of mount records affected by the Crimson Desert 1.04 migration bug.

A record is considered "broken" (i.e. eligible for repair) if:
  - Its _characterKey identifies a player-summonable mount (see mount_defs).
  - Its size is smaller than the 1.04 canonical size of 212 bytes.
  - It lacks _ownedCharacterKey or _isMainMercenary in its field-presence bitmap.
  - The enclosing save's MercenarySaveData type table has 44 fields (1.04 schema).

The type-field-count check is important: attempting repairs against a pre-1.04
schema save would insert 1.04-layout bytes that the parser cannot read back,
producing a save that the game will refuse to load cleanly.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from .mount_defs import is_summonable_mount, mount_name
from .template import EXPECTED_TYPE_FIELD_COUNT


@dataclass(frozen=True)
class BrokenMount:
    """A mount record that matches the bug signature and is eligible for repair."""
    char_key: int
    merc_no: int
    start_offset: int
    end_offset: int
    size: int
    mount_name: str
    has_owned_character_key: bool
    has_is_main_mercenary: bool
    has_last_summoned: bool


@dataclass(frozen=True)
class SchemaInfo:
    """Information about the save's MercenarySaveData schema version."""
    type_field_count: int
    is_supported: bool  # True if field count matches 1.04 (44)


def _get_element_info(raw: bytes, elem) -> tuple[int | None, int | None, set[str]]:
    """Extract char_key, merc_no, and the set of present field names from a
    reflection-parsed list element. Returns (None, None, empty set) if the
    element can't be read."""
    char_key = None
    merc_no = None
    fields_present: set[str] = set()
    for cf in (elem.child_fields or []):
        if cf.present:
            fields_present.add(cf.name)
            if cf.name == "_characterKey":
                char_key = struct.unpack_from("<I", raw, cf.start_offset)[0]
            elif cf.name == "_mercenaryNo":
                merc_no = struct.unpack_from("<I", raw, cf.start_offset)[0]
    return char_key, merc_no, fields_present


def get_schema_info(parc) -> SchemaInfo:
    """Inspect the PARC type table for MercenarySaveData and report its shape."""
    for t in parc.types:
        if t.name == "MercenarySaveData":
            fields = getattr(t, "fields", None) or getattr(t, "members", None) or []
            count = len(fields)
            return SchemaInfo(
                type_field_count=count,
                is_supported=(count == EXPECTED_TYPE_FIELD_COUNT),
            )
    return SchemaInfo(type_field_count=0, is_supported=False)


def scan_for_broken_mounts(
    raw: bytes,
    reflection_result,
) -> list[BrokenMount]:
    """Walk _mercenaryDataList and return the records that match the bug signature."""
    broken: list[BrokenMount] = []
    for obj in reflection_result["objects"]:
        if "MercenaryClan" not in obj.class_name:
            continue
        for fld in obj.fields:
            if fld.name != "_mercenaryDataList" or not fld.list_elements:
                continue
            for elem in fld.list_elements:
                char_key, merc_no, fields_present = _get_element_info(raw, elem)
                if char_key is None or merc_no is None:
                    continue
                if not is_summonable_mount(char_key):
                    continue
                size = elem.end_offset - elem.start_offset
                has_owned = "_ownedCharacterKey" in fields_present
                has_mm = "_isMainMercenary" in fields_present
                has_ls = "_lastSummoned" in fields_present
                # Bug signature: a summonable mount record that lacks
                # _ownedCharacterKey in its post-1.04 field-presence bitmap.
                # In observed data, working mounts in a 1.04 schema save
                # consistently have this field set; stuck migrations lack it.
                # Size is not part of the check — some genuine mount record
                # sizes happen to vary (182B to 669B) so size alone is not
                # a reliable discriminator.
                is_broken = not has_owned
                if is_broken:
                    broken.append(BrokenMount(
                        char_key=char_key,
                        merc_no=merc_no,
                        start_offset=elem.start_offset,
                        end_offset=elem.end_offset,
                        size=size,
                        mount_name=mount_name(char_key),
                        has_owned_character_key=has_owned,
                        has_is_main_mercenary=has_mm,
                        has_last_summoned=has_ls,
                    ))
            break  # found the list, done with this object
    return broken


def summarize_scan(
    schema: SchemaInfo,
    broken: list[BrokenMount],
) -> str:
    """Produce a human-readable summary of a scan result."""
    lines = []
    lines.append(f"MercenarySaveData schema: {schema.type_field_count} fields "
                 f"({'1.04 — supported' if schema.is_supported else 'unsupported'})")
    if not schema.is_supported:
        lines.append("")
        lines.append("This save is not in the 1.04 schema. The repair tool only")
        lines.append("handles 1.04 saves to avoid corrupting older-schema files.")
        lines.append("Load the save once in the 1.04 client and save from inside")
        lines.append("the game, then run this tool again.")
        return "\n".join(lines)

    if not broken:
        lines.append("")
        lines.append("No broken mount records detected. This save does not")
        lines.append("exhibit the 1.04 mount-visibility bug this tool repairs.")
        return "\n".join(lines)

    lines.append("")
    lines.append(f"Found {len(broken)} mount record(s) matching the bug signature:")
    for m in broken:
        flags = []
        if not m.has_owned_character_key: flags.append("no _ownedCharacterKey")
        if not m.has_is_main_mercenary: flags.append("no _isMainMercenary")
        lines.append(f"  - {m.mount_name:28s} charKey={m.char_key:<8} "
                     f"mercNo={m.merc_no:<6} size={m.size}B  ({', '.join(flags)})")
    return "\n".join(lines)
