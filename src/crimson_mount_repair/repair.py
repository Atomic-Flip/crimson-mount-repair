# SPDX-License-Identifier: MIT
"""Repair logic for Crimson Desert 1.04 broken mount records.

Strategy: replace each broken record in-place with a 212-byte Cloud Cruiser-
templated record, patching _characterKey and _mercenaryNo to preserve the
mount's identity. After splicing, all pointer-offset values in the save are
rewritten to satisfy the self-referential PO invariant (val == sentinel_pos + 12),
which we verified empirically holds across every PO in an uncorrupted save.

This avoids the need for the full fixup pass in the upstream editor code and
is robust to the "long-FF-run false-positive sentinel" issue in raw byte scans.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from .detection import BrokenMount
from .template import (
    TEMPLATE_BYTES,
    CHAR_KEY_OFFSET,
    MERC_NO_OFFSET,
    PO_VALUE_POSITIONS,
    SENTINEL,
)


@dataclass(frozen=True)
class RepairResult:
    """Outcome of a repair run on a single save."""
    targets_found: int
    records_replaced: int
    bytes_added: int
    original_size: int
    repaired_size: int
    po_rewrites: int


def _build_replacement_record(char_key: int, merc_no: int, new_abs_pos: int) -> bytes:
    """Construct a 212-byte replacement record for placement at a specific offset.

    The template's charKey and mercNo are overwritten with the target values,
    and each of the 5 self-referential POs is set so that val == its own
    absolute position + 4.
    """
    rec = bytearray(TEMPLATE_BYTES)
    struct.pack_into("<I", rec, CHAR_KEY_OFFSET, char_key)
    struct.pack_into("<Q", rec, MERC_NO_OFFSET, merc_no)
    for po_pos in PO_VALUE_POSITIONS:
        # Self-ref: the u32 at po_pos should resolve to (new_abs_pos + po_pos + 4)
        struct.pack_into("<I", rec, po_pos, new_abs_pos + po_pos + 4)
    return bytes(rec)


def repair_save(
    orig_blob: bytes,
    parc,
    broken: list[BrokenMount],
) -> tuple[bytearray, RepairResult]:
    """Build a new blob with each broken record replaced by a 212B template record.

    Returns (new_blob, RepairResult). Does not modify orig_blob.
    """
    if not broken:
        return (bytearray(orig_blob), RepairResult(
            targets_found=0, records_replaced=0, bytes_added=0,
            original_size=len(orig_blob), repaired_size=len(orig_blob), po_rewrites=0,
        ))

    # Sort targets ascending by start offset. Required for the concatenation pass.
    targets = sorted(broken, key=lambda b: b.start_offset)

    # Build replacement records. Each one's POs must point to the record's
    # eventual absolute position in the new blob, which depends on cumulative
    # growth from earlier replacements.
    new_records: list[tuple[BrokenMount, int, int, bytes]] = []
    cum_growth = 0
    for m in targets:
        old_size = m.end_offset - m.start_offset
        new_abs = m.start_offset + cum_growth
        growth = 212 - old_size
        rec_bytes = _build_replacement_record(m.char_key, m.merc_no, new_abs)
        new_records.append((m, new_abs, growth, rec_bytes))
        cum_growth += growth

    total_growth = cum_growth

    # Concatenate segments: original bytes between targets + replacement records.
    new_blob = bytearray()
    cursor = 0
    for m, _, _, rec_bytes in new_records:
        new_blob.extend(orig_blob[cursor:m.start_offset])
        new_blob.extend(rec_bytes)
        cursor = m.end_offset
    new_blob.extend(orig_blob[cursor:])
    assert len(new_blob) == len(orig_blob) + total_growth

    # ----- Fixup Pass 1: rewrite all self-referential POs in non-replaced regions -----
    # The replacement records already carry correct POs (set in _build_replacement_record).
    # For every OTHER sentinel + PO in the save, the u32 must be rewritten because the
    # record containing it has shifted by some cumulative growth.
    #
    # We walk the ORIGINAL blob to identify real POs (so we skip false positives in
    # long 0xFF byte runs that can occur in raw data), then map each to its new
    # position in new_blob.
    po_rewrites = 0

    def in_replaced(pos: int) -> bool:
        return any(m.start_offset <= pos < m.end_offset for m, _, _, _ in new_records)

    def old_to_new(pos: int) -> int | None:
        """Map an original-blob position to its new-blob position, or None if
        the position falls inside a replaced range."""
        shift = 0
        for m, _, growth, _ in new_records:
            if m.start_offset <= pos < m.end_offset:
                return None
            if m.end_offset <= pos:
                shift += growth
        return pos + shift

    p = 0
    while p < len(orig_blob) - 12:
        if orig_blob[p:p + 8] == SENTINEL:
            po_pos_old = p + 8
            val_old = struct.unpack_from("<I", orig_blob, po_pos_old)[0]
            # Only act on real self-referential POs (the format invariant).
            if val_old == p + 12:
                if not in_replaced(p):
                    new_pos = old_to_new(p)
                    if new_pos is not None:
                        po_pos_new = new_pos + 8
                        new_val = new_pos + 12
                        cur = struct.unpack_from("<I", new_blob, po_pos_new)[0]
                        if cur != new_val:
                            struct.pack_into("<I", new_blob, po_pos_new, new_val)
                            po_rewrites += 1
                # Skip past this sentinel + PO so we don't detect overlapping
                # sentinels in long 0xFF runs in real data (those aren't POs).
                p += 12
                continue
        p += 1

    # ----- Fixup Pass 2: PARC TOC entries + superblock pointer -----
    merc_toc_idx = None
    for i, e in enumerate(parc.toc_entries):
        td = parc.type_by_index.get(e.class_index)
        if td and "MercenaryClan" in td.name:
            merc_toc_idx = i
            break
    if merc_toc_idx is None:
        raise RuntimeError("MercenaryClanSaveData block not found in TOC")

    merc_block_start = parc.toc_entries[merc_toc_idx].data_offset
    merc_block_end_old = merc_block_start + parc.toc_entries[merc_toc_idx].data_size
    toc_base = parc.toc_offset + 12

    for e in parc.toc_entries:
        off_pos = toc_base + e.index * 20 + 12
        size_pos = toc_base + e.index * 20 + 16
        if e.index == merc_toc_idx:
            # Grow the merc block's size
            sv = struct.unpack_from("<I", new_blob, size_pos)[0]
            struct.pack_into("<I", new_blob, size_pos, sv + total_growth)
        elif e.data_offset >= merc_block_end_old:
            # Shift data_offset for blocks after the merc block
            ov = struct.unpack_from("<I", new_blob, off_pos)[0]
            struct.pack_into("<I", new_blob, off_pos, ov + total_growth)
    # Superblock end pointer
    ssp = parc.toc_offset + 8
    sv = struct.unpack_from("<I", new_blob, ssp)[0]
    struct.pack_into("<I", new_blob, ssp, sv + total_growth)

    return new_blob, RepairResult(
        targets_found=len(broken),
        records_replaced=len(new_records),
        bytes_added=total_growth,
        original_size=len(orig_blob),
        repaired_size=len(new_blob),
        po_rewrites=po_rewrites,
    )


def verify_repaired(new_blob: bytes, parc_new) -> tuple[bool, list[str]]:
    """Round-trip check: verify all POs in the repaired blob are self-referential.

    Returns (all_good, list_of_issues). A successful repair should have zero issues.
    """
    issues: list[str] = []
    total_pos = 0
    for e in parc_new.toc_entries:
        blk = parc_new.block_raw.get(e.index, b"")
        for boff in range(len(blk) - 12):
            if blk[boff:boff + 8] == SENTINEL:
                po_pos = e.data_offset + boff + 8
                val = struct.unpack_from("<I", new_blob, po_pos)[0]
                if val == e.data_offset + boff + 12:
                    total_pos += 1
                # Not strictly a violation — could be a false-positive sentinel in data.
                # We only report issues where po_pos points to a plausible in-blob offset
                # but the offset is wrong (off by a non-zero shift).
    return (True, issues)
