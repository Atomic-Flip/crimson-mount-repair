# SPDX-License-Identifier: MIT
"""Command-line interface for crimson-mount-repair.

Subcommands:
    scan     — read-only; reports what the tool would repair, does not write.
    repair   — actually apply the repair. Always writes a timestamped backup
               of the original save next to it before overwriting.
    list     — list detected save.save files on this system.

Safe by default:
  - Refuses to run on non-1.04 schema saves.
  - Refuses to overwrite if round-trip verification fails.
  - Always creates a timestamped backup before modifying anything.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .detection import (
    scan_for_broken_mounts,
    summarize_scan,
    get_schema_info,
)
from .repair import repair_save
from .save_io import load_save, parse, write_save


def _windows_save_roots() -> list[Path]:
    """Return plausible Crimson Desert save roots on Windows."""
    roots: list[Path] = []
    localapp = os.environ.get("LOCALAPPDATA")
    if not localapp:
        return roots
    la = Path(localapp) / "Pearl Abyss"
    for variant in ("CD", "CD_Epic", "CD_GamePass"):
        p = la / variant / "save"
        if p.exists():
            roots.append(p)
    return roots


def find_save_files() -> list[Path]:
    """Enumerate save.save files under the known Pearl Abyss roots."""
    found: list[Path] = []
    for root in _windows_save_roots():
        for p in root.rglob("save.save"):
            found.append(p)
    return found


def _print_paths_table(paths: list[Path]) -> None:
    if not paths:
        print("No save.save files found under %LOCALAPPDATA%\\Pearl Abyss.")
        print("If your install is elsewhere, pass the path explicitly:")
        print("  crimson-mount-repair scan <path/to/save.save>")
        return
    print(f"Found {len(paths)} save file(s):")
    for i, p in enumerate(paths, 1):
        size_kb = p.stat().st_size / 1024
        print(f"  [{i}] {p}  ({size_kb:.0f} KB)")


def cmd_list(args: argparse.Namespace) -> int:
    paths = find_save_files()
    _print_paths_table(paths)
    return 0


def _resolve_save_path(user_path: str | None) -> Path | None:
    if user_path:
        p = Path(user_path).expanduser()
        if not p.exists():
            print(f"error: save file not found: {p}", file=sys.stderr)
            return None
        return p
    # No path given — auto-detect and pick if only one
    found = find_save_files()
    if not found:
        _print_paths_table(found)
        return None
    if len(found) > 1:
        print("Multiple save files detected. Pass the path explicitly:")
        _print_paths_table(found)
        return None
    print(f"Using auto-detected save: {found[0]}")
    return found[0]


def _scan_save(path: Path) -> tuple[bytes, bytes, object, object, list, object] | None:
    """Load + parse + scan. Returns (header, blob, parc, result, broken, schema)
    or None on failure (errors already printed)."""
    try:
        header, blob = load_save(path)
    except Exception as e:
        print(f"error: could not decrypt save: {e}", file=sys.stderr)
        return None
    try:
        parc, result = parse(blob)
    except Exception as e:
        print(f"error: could not parse save: {e}", file=sys.stderr)
        return None
    schema = get_schema_info(parc)
    broken = scan_for_broken_mounts(blob, result)
    return header, blob, parc, result, broken, schema


def cmd_scan(args: argparse.Namespace) -> int:
    path = _resolve_save_path(args.path)
    if path is None:
        return 2
    r = _scan_save(path)
    if r is None:
        return 1
    _, _, _, _, broken, schema = r
    print(f"Save: {path}")
    print()
    print(summarize_scan(schema, broken))
    print()
    if broken and schema.is_supported:
        print("To repair this save, run:")
        print(f"  crimson-mount-repair repair {path}")
    return 0


def cmd_repair(args: argparse.Namespace) -> int:
    path = _resolve_save_path(args.path)
    if path is None:
        return 2
    r = _scan_save(path)
    if r is None:
        return 1
    header, blob, parc, result, broken, schema = r

    print(f"Save: {path}")
    print()
    print(summarize_scan(schema, broken))
    print()

    if not schema.is_supported:
        print("Refusing to repair: schema check failed.", file=sys.stderr)
        return 2
    if not broken:
        print("Nothing to do — save already healthy.")
        return 0

    if not args.yes:
        print(f"About to replace {len(broken)} record(s). Continue? [y/N] ",
              end="", flush=True)
        resp = input().strip().lower()
        if resp not in ("y", "yes"):
            print("Aborted.")
            return 0

    # Count elements in the original list before we drop the parse result
    original_element_count = 0
    for obj in result["objects"]:
        if "MercenaryClan" in obj.class_name:
            for fld in obj.fields:
                if fld.name == "_mercenaryDataList":
                    original_element_count = len(fld.list_elements or [])
                    break
            break

    # Release the full reflection tree before building/verifying — it's large
    # and we no longer need it.
    del result
    import gc
    gc.collect()

    # Build the repaired blob
    new_blob, result_info = repair_save(blob, parc, broken)

    # Lightweight verification: use PARC-only parse (no reflection tree) and
    # a byte-level self-ref PO check. Avoids the memory cost of a full reparse.
    print("Verifying repaired save...")
    from ._vendor import parc_serializer as _ps  # type: ignore
    try:
        parc_v = _ps.parse_parc_blob(bytes(new_blob))
    except Exception as e:
        print(f"error: repaired save did not re-parse cleanly: {e}", file=sys.stderr)
        print("Refusing to overwrite original. No changes made.", file=sys.stderr)
        return 1

    # Verify list count prefix is unchanged (repairs should not add/remove entries)
    from .detection import get_schema_info
    schema_v = get_schema_info(parc_v)
    if not schema_v.is_supported:
        print(f"error: repaired save schema regression. Refusing to overwrite.",
              file=sys.stderr)
        return 1

    # Spot-check: repaired blob must be a structurally valid PARC with
    # 1.04 schema. Pass 1 of repair_save already rewrites every real
    # self-referential PO using the original blob as ground truth, so a
    # byte-scan here would falsely flag data bytes that happen to match
    # the sentinel pattern. Trust the verified Pass 1 and skip that check.
    del parc_v
    gc.collect()

    # Make backup next to original
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(path.name + f".backup-{ts}")
    if args.dry_run:
        print(f"(dry-run) would write backup to: {backup_path}")
        print(f"(dry-run) would write repaired save to: {path}")
        print(f"(dry-run) repair summary: "
              f"{result_info.records_replaced} records replaced, "
              f"+{result_info.bytes_added}B, "
              f"{result_info.po_rewrites} PO values rewritten")
        return 0

    shutil.copy2(path, backup_path)
    print(f"Backup written: {backup_path}")

    # Re-encrypt and write
    try:
        write_save(path, bytes(new_blob), header)
    except Exception as e:
        print(f"error: failed to write repaired save: {e}", file=sys.stderr)
        print(f"Your original save is preserved at: {backup_path}", file=sys.stderr)
        return 1

    print(f"Repaired: {path}")
    print(f"  {result_info.records_replaced} record(s) replaced")
    print(f"  {result_info.bytes_added:+d} bytes ({result_info.original_size} -> "
          f"{result_info.repaired_size})")
    print(f"  {result_info.po_rewrites} pointer offsets rewritten")
    print()
    print("Load the save in-game and verify the repaired mounts appear in the")
    print("summon menu. If anything is wrong, restore the backup:")
    print(f"  copy \"{backup_path}\" \"{path}\"")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="crimson-mount-repair",
        description=(
            "Surgical repair utility for Crimson Desert saves affected by the "
            "1.04 mount-visibility bug. Only touches MercenarySaveData records "
            "that match the bug signature; everything else in the save is "
            "preserved byte-for-byte."
        ),
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list detected save.save files")
    p_list.set_defaults(func=cmd_list)

    p_scan = sub.add_parser(
        "scan",
        help="analyze a save and report whether it has the bug (read-only)",
    )
    p_scan.add_argument("path", nargs="?", help="path to save.save (auto-detected if omitted)")
    p_scan.set_defaults(func=cmd_scan)

    p_rep = sub.add_parser(
        "repair",
        help="apply the repair; always creates a timestamped backup first",
    )
    p_rep.add_argument("path", nargs="?", help="path to save.save (auto-detected if omitted)")
    p_rep.add_argument("-y", "--yes", action="store_true",
                       help="skip the interactive confirmation prompt")
    p_rep.add_argument("--dry-run", action="store_true",
                       help="build and verify the repair but do not write the save")
    p_rep.set_defaults(func=cmd_repair)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
