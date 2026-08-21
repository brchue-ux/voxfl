"""``python -m voxfl.vital`` — drive Vital headlessly and render presets.

Start with ``probe``. It answers the question the corpus build depends on:
which route can actually get a .vital preset into the hosted plugin?
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .render import RenderError, VitalHost, audio_summary, parse_state, write_wav
from .vitalfile import Preset, VitalFileError

DEFAULT_VST3 = r"C:\Program Files\Common Files\VST3\Vital.vst3"


def _host(args: argparse.Namespace) -> VitalHost:
    return VitalHost(args.plugin)


def cmd_probe(args: argparse.Namespace) -> int:
    print(f"loading {args.plugin} ...")
    host = _host(args)
    params = host.parameters()
    print(f"  loaded: {host.synth.get_name()}")
    print(f"  {len(params)} host parameters exposed")
    print(f"  {host.synth.get_num_output_channels()} output channels\n")

    if params:
        print("  first few parameters:")
        for entry in params[:8]:
            print(f"    [{entry.get('index'):>4}] {entry.get('name')}")
        print()

    # Route 3 first: does rendering work at all?
    print("route 'none' — render the default patch")
    audio = host.render_note()
    summary = audio_summary(audio)
    silent = summary["peak"] < 1e-5
    print(f"  peak {summary['peak']:.4f}  rms {summary['rms']:.4f}  "
          f"{summary['seconds']:.2f}s  ->  {'SILENT' if silent else 'ok, made sound'}")
    if args.out:
        print(f"  wrote {write_wav(Path(args.out) / 'probe_default.wav', audio)}")
    print()

    # Route 1: is the plugin state really the preset JSON?
    print("route 'state' — is Vital's plugin state the preset JSON?")
    state_path = Path(args.out or ".") / "probe_state.bin"
    blob = host.dump_state(state_path)
    print(f"  state file: {len(blob.raw)} bytes -> {state_path}")
    if blob.payload is None:
        print("  no JSON object found in the state blob")
        print("  => route 'state' NOT available; fall back to 'params'")
    else:
        keys = ", ".join(list(blob.payload)[:8])
        print(f"  JSON found at byte {blob.json_start}, "
              f"{len(blob.raw) - (blob.json_end or 0)} trailing bytes")
        print(f"  top-level keys: {keys}")
        if blob.holds_vital_json:
            print("  => route 'state' AVAILABLE — presets can be injected wholesale")
        else:
            print("  => JSON present but does not look like a Vital preset")

    # Route 2: how much of a preset can parameter-matching cover?
    if args.preset:
        print("\nroute 'params' — how much of a preset do host parameters cover?")
        preset = Preset.load(args.preset)
        index = host.parameter_index()
        wanted = preset.params()
        matched = [k for k in wanted if _norm(k) in index]
        coverage = 100.0 * len(matched) / len(wanted) if wanted else 0.0
        print(f"  {preset.name}: {len(matched)}/{len(wanted)} parameters matched "
              f"({coverage:.0f}%)")
        missing = [k for k in wanted if _norm(k) not in index][:10]
        if missing:
            print(f"  unmatched sample: {', '.join(missing)}")
        print("  note: wavetables, modulations and LFO shapes are never host "
              "parameters, so this route is lossy even at 100%")

    print("\nprobe complete.")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    host = _host(args)
    preset = Preset.load(args.preset)
    applied = _apply(host, preset, args.route, args.out)

    audio = host.render_note(note=args.note, velocity=args.velocity, hold=args.hold)
    summary = audio_summary(audio)
    out = Path(args.out) / f"{preset.path.stem}.wav"
    write_wav(out, audio)

    print(f"{preset.name}  [{args.route}{applied}]")
    print(f"  peak {summary['peak']:.4f}  rms {summary['rms']:.4f}  -> {out}")
    if summary["peak"] < 1e-5:
        print("  WARNING: silent. The preset probably did not apply.", file=sys.stderr)
        return 1
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    presets = sorted(Path(args.dir).rglob("*.vital"))
    if not presets:
        print(f"no .vital files under {args.dir}", file=sys.stderr)
        return 1
    if args.limit:
        presets = presets[: args.limit]

    host = _host(args)
    out_dir = Path(args.out)
    started = time.monotonic()
    ok, silent, failed = 0, 0, 0

    for i, path in enumerate(presets, 1):
        try:
            preset = Preset.load(path)
            _apply(host, preset, args.route, args.out, quiet=True)
            audio = host.render_note(note=args.note, velocity=args.velocity, hold=args.hold)
            summary = audio_summary(audio)
            # Mirror the source tree so preset-pack folder names survive as role labels.
            rel = path.relative_to(args.dir).with_suffix(".wav")
            write_wav(out_dir / rel, audio)
            if summary["peak"] < 1e-5:
                silent += 1
                status = "SILENT"
            else:
                ok += 1
                status = f"peak {summary['peak']:.3f}"
        except (RenderError, VitalFileError, OSError) as exc:
            failed += 1
            status = f"FAILED {exc}"
        print(f"[{i:>4}/{len(presets)}] {path.name[:52]:<52} {status}")

    elapsed = time.monotonic() - started
    per = elapsed / len(presets)
    print(f"\n{ok} ok, {silent} silent, {failed} failed in {elapsed:.1f}s "
          f"({per:.2f}s each)")
    print(f"a 5,000-preset corpus would take about {per * 5000 / 60:.0f} minutes")
    return 0 if failed == 0 else 1


def _apply(host: VitalHost, preset: Preset, route: str, out: str, *, quiet: bool = False) -> str:
    if route == "none":
        return ""
    if route == "params":
        applied, missed = host.apply_params(preset)
        if not quiet:
            print(f"  applied {applied} parameters, {len(missed)} unmatched")
        return f" {applied}p"
    if route == "state":
        scratch = Path(out) / "_state"
        blob = host.dump_state(scratch / "current.bin")
        if blob.json_start is None:
            raise RenderError(
                "route 'state' is unavailable: no JSON found in the plugin state. "
                "Run 'probe' first, then use --route params."
            )
        injected = scratch / f"{preset.path.stem}.bin"
        injected.write_bytes(blob.rebuild_with(preset))
        host.apply_state_file(injected)
        return " state"
    raise RenderError(f"unknown route: {route}")


def _norm(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m voxfl.vital",
        description="Drive Vital headlessly through DawDreamer.",
    )
    parser.add_argument("--plugin", default=DEFAULT_VST3, help=f"path to Vital.vst3 (default: {DEFAULT_VST3})")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("probe", help="find out which preset-loading route works")
    p.add_argument("-o", "--out", default="phase0_out", help="where to write probe artefacts")
    p.add_argument("--preset", help="a .vital file, to measure parameter coverage")
    p.set_defaults(func=cmd_probe)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--route", default="state", choices=("state", "params", "none"))
    common.add_argument("--note", type=int, default=48, help="MIDI note (default 48, C2)")
    common.add_argument("--velocity", type=int, default=100)
    common.add_argument("--hold", type=float, default=1.5, help="note length in seconds")
    common.add_argument("-o", "--out", default="phase0_out")

    p = sub.add_parser("render", parents=[common], help="render one preset to wav")
    p.add_argument("preset")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("batch", parents=[common], help="render a folder of presets")
    p.add_argument("dir")
    p.add_argument("--limit", type=int, help="stop after N presets (use 100 to time it)")
    p.set_defaults(func=cmd_batch)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except RenderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except VitalFileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"error: no such file: {exc.filename}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
