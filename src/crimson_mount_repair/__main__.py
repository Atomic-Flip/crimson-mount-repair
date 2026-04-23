# SPDX-License-Identifier: MIT
"""Allow running the tool as a module: `python -m crimson_mount_repair ...`"""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
