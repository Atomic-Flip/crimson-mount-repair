# SPDX-License-Identifier: MIT
"""Thin wrapper around vendored save_crypto for load/save round trips."""
from __future__ import annotations

from pathlib import Path

# Vendored modules — imported through the package's _vendor submodule.
# We insert its path so that save_parser / parc_serializer etc. can find
# each other via their upstream absolute imports (save_parser imports save_crypto etc.).
import sys as _sys
from . import _vendor as _v

_VENDOR_DIR = str(Path(_v.__file__).parent)
if _VENDOR_DIR not in _sys.path:
    _sys.path.insert(0, _VENDOR_DIR)

import save_crypto  # type: ignore  # noqa: E402
import save_parser as _sp  # type: ignore  # noqa: E402
import parc_serializer as _ps  # type: ignore  # noqa: E402


def load_save(path: str | Path) -> tuple[bytes, bytes]:
    """Decrypt a save.save file. Returns (header, decompressed_blob).

    Raises Warning from save_crypto if HMAC mismatches (save may be corrupted).
    """
    sd = save_crypto.load_save_file(str(path))
    return bytes(sd.raw_header), bytes(sd.decompressed_blob)


def write_save(path: str | Path, blob: bytes, header: bytes) -> None:
    """Re-encrypt and write a save file, preserving the version from the header."""
    save_crypto.write_save_file(str(path), bytes(blob), bytes(header))


def parse(blob: bytes):
    """Parse a decompressed blob. Returns (parc, reflection_result)."""
    parc = _ps.parse_parc_blob(blob)
    result = _sp.build_result_from_raw(blob, {"input_kind": "raw_blob"})
    return parc, result
