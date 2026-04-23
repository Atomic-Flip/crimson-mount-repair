# SPDX-License-Identifier: MIT
"""Reference 1.04-schema MercenarySaveData record template.

This is the byte layout of a working post-1.04 mount record (specifically
a Cloud Cruiser with default ownership and summon state), captured from a
real save file. It is used as the template for repairing stuck records.

When repairing a broken mount record, this template's bytes are used
verbatim with only _characterKey (offset 27), _mercenaryNo (offset 31),
and the five self-referential pointer-offset values overwritten.

The fields this template carries that broken records lack:
  - _ownedCharacterKey = 1 (the marker the 1.04 mount menu appears to check)
  - _isMainMercenary = True
  - full 1.04-schema bitmap (member bits shifted for the new field layout)

Size: 212 bytes.
Schema: 1.04 MercenarySaveData (44-field type table).
"""
from __future__ import annotations

# 212-byte template extracted from a verified-working Cloud Cruiser record.
# Source: real save file, 1.04 client, mount summon menu populated successfully.
#
# Byte layout (for reference; do not edit the hex by hand):
#   [0:2]    mbc (member bitmap count) = 6
#   [2:8]    field-presence bitmap = 0d 19 00 3f 08 06
#   [8:11]   main type index = 0x39 (MercenarySaveData) + padding
#   [11:19]  sentinel 1 (0xFF * 8)
#   [19:23]  PO 1 value (self-referential, overwritten on placement)
#   [23:27]  filler
#   [27:31]  _characterKey u32 (overwritten per-target)
#   [31:39]  _mercenaryNo u64 (overwritten per-target)
#   [39:43]  _ownedCharacterKey u32 = 1 (the 1.04 mount-visibility marker)
#   [43+]    nested locator objects with four more sentinel/PO pairs,
#            timestamps, spawn data, and trailing body-size counter (0xB9)
TEMPLATE_HEX: str = "06000d19003f08063a0000ffffffffffffffff85bd1700000000003a4a0f0004170000000000000100000001001c3b0000ffffffffffffffffabbd1700000000000100002b0000ffffffffffffffffc1bd170000000000040000000100002b0000ffffffffffffffffdbbd170000000000040000000100002b0000fffffffffffffffff5bd1700000000000400000052000000fc0f99ee02000000fc0f99ee0200000001313624c6984f1844c26889c5da682dc00100000001010101000101012c010000000000000000000000000000b9000000"

TEMPLATE_BYTES: bytes = bytes.fromhex(TEMPLATE_HEX)
assert len(TEMPLATE_BYTES) == 212, f"template must be 212B, got {len(TEMPLATE_BYTES)}"

# Byte offsets within the template for patchable fields:
CHAR_KEY_OFFSET: int = 27       # u32 little-endian
MERC_NO_OFFSET: int = 31        # u64 little-endian

# Positions (within the record) of the five pointer-offset u32 values.
# Each follows an 8-byte sentinel (0xFF * 8) and contains a self-referential
# pointer that must equal (record_start + po_position + 4) when the record
# is placed at its final absolute offset.
PO_VALUE_POSITIONS: list[int] = [0x13, 0x39, 0x4F, 0x69, 0x83]

SENTINEL: bytes = b"\xff" * 8

# The 1.04 MercenarySaveData type table has 44 fields. Saves whose type
# table reports a different field count use a different schema (pre-1.04
# has 43, some very old betas may have fewer) and will not round-trip
# correctly with this template.
EXPECTED_TYPE_FIELD_COUNT: int = 44
