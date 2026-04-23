# SPDX-License-Identifier: MIT
"""crimson-mount-repair — Surgical repair utility for the Crimson Desert 1.04 mount bug.

This package is a single-purpose tool. It detects mount records in a Crimson Desert
save file that were silently corrupted by the 1.04 patch migration and replaces
them with well-formed 1.04-schema records. It does not edit anything else.

Quick start:
    python -m crimson_mount_repair --scan /path/to/save.save
    python -m crimson_mount_repair --repair /path/to/save.save

See README.md for background and the docs/ directory for the technical diagnosis
of the bug this tool fixes.
"""
from __future__ import annotations

__version__ = "0.1.0"
