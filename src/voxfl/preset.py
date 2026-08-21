"""Entry point so ``python -m voxfl.preset`` works."""

from .preset_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
