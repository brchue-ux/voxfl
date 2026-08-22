"""``python -m voxfl.benchmark`` — the personal benchmark harness.

[evaluation.md](../../docs/evaluation.md#the-personal-benchmark): pick ~50
presets across bass/lead/pad/pluck, listen to each, record an imitation,
save the pair. This module is that harness — it does not, and cannot,
record the captain's own voice. What it does:

- **scaffold**: stratified-sample presets from an already-built corpus
  manifest (see ``corpus.py``) and write a checklist of exactly what to
  listen to and where to save each recording.
- **ingest**: once recordings exist on disk, fold them into the benchmark
  manifest and validate each one (present, non-silent, long enough).
- **synthetic**: build a stand-in benchmark from synthetic.py so the rest of
  the pipeline (corpus build, baselines, role filtering, metrics) can be
  proven correct before real recordings exist.

Run captain-side, on Windows, after the corpus is built:

    pip install -r requirements.txt
    export PYTHONPATH=src
    python -m voxfl.benchmark scaffold corpus/manifest.jsonl -o benchmark
    # listen to each wav benchmark/TODO.md lists, record yourself imitating
    # it (any mic, 16-bit wav, a few seconds), save as
    # benchmark/recordings/<id>.wav
    python -m voxfl.benchmark ingest benchmark/manifest.jsonl benchmark/recordings -o benchmark/manifest.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np

from .corpus import CorpusItem, load_manifest as load_corpus_manifest
from .features import FeatureError, load_mono

DEFAULT_ROLES = ("bass", "lead", "pad", "pluck")


@dataclass
class BenchmarkEntry:
    id: str  # matches a CorpusItem.id
    preset_relpath: str
    role: str
    preset_wav: str | None  # a rendered variant, for the captain to listen to
    imitation_wav: str | None = None  # filled in by ingest()


class BenchmarkError(Exception):
    pass


# --------------------------------------------------------------- scaffold

def scaffold(
    corpus_items: list[CorpusItem],
    *,
    n_total: int = 50,
    roles: tuple[str, ...] = DEFAULT_ROLES,
    seed: int = 0,
) -> list[BenchmarkEntry]:
    """Stratified sample across roles, ~n_total / len(roles) each.

    evaluation.md: "include the awkward cases deliberately: sounds you find
    easy to imitate and sounds you don't ... a few where two or three
    presets in the corpus are genuinely near-identical." This picks
    uniformly at random rather than trying to detect "awkward" automatically
    — that judgement needs a human ear, so scaffold() gives an unbiased
    starting sample and leaves swapping in deliberately-awkward ones to the
    captain, by hand, before recording.
    """
    rng = np.random.default_rng(seed)
    per_role = max(1, n_total // len(roles))
    entries = []
    for role in roles:
        pool = [it for it in corpus_items if it.role == role and (it.short_wav or it.long_wav)]
        if not pool:
            continue
        k = min(per_role, len(pool))
        chosen = rng.choice(len(pool), size=k, replace=False)
        for i in chosen:
            item = pool[int(i)]
            entries.append(
                BenchmarkEntry(
                    id=item.id,
                    preset_relpath=item.preset_relpath,
                    role=item.role,
                    preset_wav=item.long_wav or item.short_wav,
                )
            )
    return entries


def write_checklist(entries: list[BenchmarkEntry], path: str | Path) -> Path:
    lines = [
        f"# Phase 1 personal benchmark — {len(entries)} presets to imitate",
        "",
        "For each row: listen to the wav, then record yourself imitating it",
        "(any mic, a few seconds, 16-bit wav) and save it at the given path.",
        "",
    ]
    for e in entries:
        lines.append(f"- [ ] `{e.id}` ({e.role}) — listen: `{e.preset_wav}`")
        lines.append(f"      save as: `recordings/{e.id}.wav`")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


# ------------------------------------------------------------------ ingest

def _validate_recording(path: Path) -> None:
    try:
        mono, rate = load_mono(path)
    except FeatureError as exc:
        raise BenchmarkError(str(exc)) from exc
    if mono.size == 0:
        raise BenchmarkError(f"{path}: empty recording")
    if float(np.max(np.abs(mono))) < 1e-4:
        raise BenchmarkError(f"{path}: recording is silent")
    if mono.size / rate < 0.2:
        raise BenchmarkError(f"{path}: recording too short ({mono.size / rate:.2f}s)")


def ingest(
    entries: list[BenchmarkEntry], recordings_dir: str | Path
) -> tuple[list[BenchmarkEntry], list[str], list[str]]:
    """Fill in ``imitation_wav`` for every entry with a matching recording.

    Returns (updated_entries, missing_ids, invalid). A recording that fails
    validation is reported in ``invalid`` and left unfilled rather than
    silently accepted, so a bad take doesn't quietly poison the benchmark.
    """
    recordings_dir = Path(recordings_dir)
    missing, invalid, updated = [], [], []
    for e in entries:
        candidate = recordings_dir / f"{e.id}.wav"
        if not candidate.is_file():
            missing.append(e.id)
            updated.append(e)
            continue
        try:
            _validate_recording(candidate)
        except BenchmarkError as exc:
            invalid.append(f"{e.id}: {exc}")
            updated.append(e)
            continue
        updated.append(replace(e, imitation_wav=str(candidate)))
    return updated, missing, invalid


# -------------------------------------------------------------- persistence

def save_manifest(entries: list[BenchmarkEntry], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for e in entries:
            fh.write(json.dumps(asdict(e)) + "\n")
    return path


def load_manifest(path: str | Path) -> list[BenchmarkEntry]:
    entries = []
    with Path(path).open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                entries.append(BenchmarkEntry(**json.loads(line)))
    return entries


def ready_entries(entries: list[BenchmarkEntry]) -> list[BenchmarkEntry]:
    """Entries that actually have an ingested recording — what evaluate.py can use."""
    return [e for e in entries if e.imitation_wav]


# ----------------------------------------------------------------------- cli

def cmd_scaffold(args: argparse.Namespace) -> int:
    corpus_items = load_corpus_manifest(args.corpus_manifest)
    entries = scaffold(corpus_items, n_total=args.n, roles=tuple(args.roles.split(",")), seed=args.seed)
    if not entries:
        print("no corpus items matched the requested roles", file=sys.stderr)
        return 1
    out = Path(args.out)
    manifest_path = save_manifest(entries, out / "manifest.jsonl")
    checklist_path = write_checklist(entries, out / "TODO.md")
    counts: dict[str, int] = {}
    for e in entries:
        counts[e.role] = counts.get(e.role, 0) + 1
    print(f"scaffolded {len(entries)} entries: {counts}")
    print(f"wrote {manifest_path}")
    print(f"wrote {checklist_path} — start here")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    entries = load_manifest(args.manifest)
    updated, missing, invalid = ingest(entries, args.recordings_dir)
    save_manifest(updated, args.out or args.manifest)
    ready = ready_entries(updated)
    print(f"{len(ready)}/{len(updated)} entries have a recording")
    if invalid:
        print(f"{len(invalid)} recordings failed validation:")
        for line in invalid:
            print(f"  {line}")
    if missing:
        print(f"{len(missing)} still missing, e.g.: {', '.join(missing[:10])}")
    return 0 if not invalid else 1


def cmd_synthetic(args: argparse.Namespace) -> int:
    from .synthetic import build_synthetic_benchmark, build_synthetic_corpus  # noqa: PLC0415

    out = Path(args.out)
    presets, short_dir, long_dir = build_synthetic_corpus(out / "corpus", per_role=args.per_role, seed=args.seed)
    recordings = build_synthetic_benchmark(presets, out, seed=args.seed + 1)

    from .corpus import _item_id  # noqa: PLC0415

    entries = [
        BenchmarkEntry(
            # Must match corpus.build_manifest()'s id scheme exactly, since
            # that's what pairs a benchmark entry to its corpus embedding.
            id=_item_id(Path(p.role) / p.id),
            preset_relpath=f"{p.role}/{p.id}.vital",
            role=p.role,
            preset_wav=str(long_dir / p.role / f"{p.id}.wav"),
            imitation_wav=str(recordings / f"{p.id}.wav"),
        )
        for p in presets
    ]
    manifest_path = save_manifest(entries, out / "manifest.jsonl")
    print(f"SYNTHETIC benchmark: {len(entries)} presets, {short_dir} / {long_dir} corpus wavs")
    print(f"wrote {manifest_path}")
    print("this is placeholder data for pipeline validation only — not a real benchmark")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m voxfl.benchmark",
        description="Build and ingest the Phase 1 personal benchmark.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scaffold", help="stratified-sample presets to record against")
    p.add_argument("corpus_manifest", help="corpus manifest.jsonl from voxfl.corpus")
    p.add_argument("-o", "--out", default="benchmark")
    p.add_argument("-n", type=int, default=50)
    p.add_argument("--roles", default=",".join(DEFAULT_ROLES))
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(func=cmd_scaffold)

    p = sub.add_parser("ingest", help="fold recordings into the benchmark manifest")
    p.add_argument("manifest")
    p.add_argument("recordings_dir")
    p.add_argument("-o", "--out", help="output path (default: overwrite the input manifest)")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("synthetic", help="build a synthetic corpus+benchmark for pipeline validation")
    p.add_argument("-o", "--out", default="synthetic_benchmark")
    p.add_argument("--per-role", type=int, default=15)
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(func=cmd_synthetic)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except BenchmarkError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"error: no such file: {exc.filename}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
