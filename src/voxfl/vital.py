"""Entry point so ``python -m voxfl.vital`` works."""

from .render_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
