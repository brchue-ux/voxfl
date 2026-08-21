"""``python -m voxfl.preset`` — inspect and edit Vital presets from the shell.

Phase 0 tool #1. The round-trip test lives in ``set``/``nudge``: change a
value, write the file, open it in Vital, confirm it sounds different.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .vitalfile import Preset, VitalFileError, diff


def _fmt(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, str):
        return value if len(value) <= 60 else value[:57] + "..."
    return str(value)


def cmd_inspect(args: argparse.Namespace) -> int:
    preset = Preset.load(args.file)
    flat = preset.flatten(include_bulk=args.all)

    if args.match:
        needle = args.match.lower()
        flat = {k: v for k, v in flat.items() if needle in k.lower()}

    if args.json:
        print(json.dumps(flat, indent=2, sort_keys=True))
        return 0

    meta = preset.meta()
    print(f"{preset.path.name}  ({preset.path.stat().st_size / 1024:.1f} KB"
          f"{', gzipped' if preset.was_gzipped else ''})")
    if meta:
        print()
        for key, value in meta.items():
            print(f"  {key:<24} {_fmt(value)}")

    print(f"\n  {len(preset.params())} numeric parameters under settings")
    print(f"  {len(preset.flatten())} scalars total\n")

    if not flat:
        print(f"  no paths matching {args.match!r}")
        return 1

    width = min(max(len(k) for k in flat), 52)
    for key in sorted(flat):
        print(f"  {key:<{width}}  {_fmt(flat[key])}")
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    preset = Preset.load(args.file)
    try:
        print(_fmt(preset.get(args.path)))
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _parse_value(text: str) -> object:
    for caster in (int, float):
        try:
            return caster(text)
        except ValueError:
            pass
    lowered = text.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    return text


def cmd_set(args: argparse.Namespace) -> int:
    preset = Preset.load(args.file)
    value = _parse_value(args.value)
    try:
        before = preset.set(args.path, value)
    except KeyError as exc:
        print(f"error: {exc}\nhint: run 'inspect --match {args.path.split('.')[-1]}' "
              f"to find the real path", file=sys.stderr)
        return 1

    out = Path(args.out) if args.out else _suffixed(preset.path, args.path, value)
    preset.save(out)
    print(f"{args.path}: {_fmt(before)} -> {_fmt(value)}")
    print(f"wrote {out}")
    return 0


def cmd_nudge(args: argparse.Namespace) -> int:
    preset = Preset.load(args.file)
    try:
        before, after = preset.nudge(args.path, args.delta)
    except (KeyError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    out = Path(args.out) if args.out else _suffixed(preset.path, args.path, after)
    preset.save(out)
    print(f"{args.path}: {_fmt(before)} -> {_fmt(after)}  ({args.delta:+g})")
    print(f"wrote {out}")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    a, b = Preset.load(args.a), Preset.load(args.b)
    result = diff(a, b, include_bulk=args.all)

    if not result:
        print("identical (no scalar differences)")
        return 0

    print(f"{a.path.name} -> {b.path.name}   {result.total} difference"
          f"{'s' if result.total != 1 else ''}\n")
    for key, (old, new) in sorted(result.changed.items()):
        print(f"  ~ {key}\n      {_fmt(old)}  ->  {_fmt(new)}")
    for key, value in sorted(result.added.items()):
        print(f"  + {key} = {_fmt(value)}")
    for key, value in sorted(result.removed.items()):
        print(f"  - {key} (was {_fmt(value)})")
    return 0


def _suffixed(path: Path, changed: str, value: object) -> Path:
    leaf = changed.split(".")[-1]
    return path.with_name(f"{path.stem}__{leaf}_{_fmt(value).replace('.', 'p')}{path.suffix}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m voxfl.preset",
        description="Inspect and edit Vital .vital preset files.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("inspect", help="list everything inside a preset")
    p.add_argument("file")
    p.add_argument("-m", "--match", help="only paths containing this substring, e.g. cutoff")
    p.add_argument("--all", action="store_true", help="include bulk arrays (wavetable data)")
    p.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("get", help="print one value")
    p.add_argument("file")
    p.add_argument("path", help="dotted path, e.g. settings.filter_1_cutoff")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("set", help="set one value and write a new preset")
    p.add_argument("file")
    p.add_argument("path")
    p.add_argument("value")
    p.add_argument("-o", "--out", help="output path (default: alongside the input)")
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("nudge", help="add a delta to a numeric value")
    p.add_argument("file")
    p.add_argument("path")
    p.add_argument("delta", type=float, help="e.g. 12 or -0.15")
    p.add_argument("-o", "--out")
    p.set_defaults(func=cmd_nudge)

    p = sub.add_parser(
        "diff",
        help="compare two presets — the fastest way to learn parameter names",
    )
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--all", action="store_true", help="include bulk arrays")
    p.set_defaults(func=cmd_diff)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except VitalFileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"error: no such file: {exc.filename}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
