"""Build and embed the preset corpus — Phase 1 step 2.

Rendering itself is Phase 0's job, untouched: run ``python -m voxfl.vital
batch`` twice (once per note length) as documented in docs/phase1.md, mirror
the preset folder tree into two wav trees, and *then* hand both trees to
:func:`build_manifest` here, which does the two things Phase 1 actually adds:

- Tag each preset's **role** from its top-level source folder
  (architecture.md: "preset packs are almost always organised into Bass/,
  Lead/, Pad/, Pluck/ folders — that folder structure is free role labels").
- Pair up the short/long renderings (architecture.md: "attack and sustain
  carry different information") into one :class:`CorpusItem` per preset.

:func:`embed_manifest` then turns each item into a vector with whichever
:mod:`embed` baseline is asked for, averaging the short/long variant vectors
into one preset-level embedding (the benchmark's ground truth is per-preset,
not per-variant).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .embed import ClapUnavailable, Embedder, FeatureEmbedder, RandomEmbedder
from .features import NormStats, features_from_file

# Maps a lowercased top-level source folder name to a canonical role. Extend
# this as real preset packs turn up spellings not covered here — it is
# intentionally not exhaustive, and "other" is a legitimate role, not a bug.
ROLE_ALIASES = {
    "bass": "bass",
    "basses": "bass",
    "bassline": "bass",
    "sub": "bass",
    "lead": "lead",
    "leads": "lead",
    "pad": "pad",
    "pads": "pad",
    "pluck": "pluck",
    "plucks": "pluck",
    "keys": "pluck",
}
ROLES = ("bass", "lead", "pad", "pluck", "other")


def role_from_path(preset_relpath: str | Path) -> str:
    """The role is the first path component, mapped through ROLE_ALIASES."""
    parts = Path(preset_relpath).parts
    if not parts:
        return "other"
    return ROLE_ALIASES.get(parts[0].lower(), "other")


@dataclass
class CorpusItem:
    id: str  # stable id: the preset's relative path with '/' -> '__'
    preset_relpath: str
    role: str
    short_wav: str | None
    long_wav: str | None


def _item_id(relpath: Path) -> str:
    return str(relpath.with_suffix("")).replace("\\", "/").replace("/", "__")


def build_manifest(short_dir: Path, long_dir: Path) -> list[CorpusItem]:
    """Pair up two ``voxfl.vital batch`` output trees into corpus items.

    A preset missing one of the two variants is still included (some
    corpora are single-shot presets that never sustain) — evaluate.py and
    embed_manifest() both tolerate a missing wav.
    """
    short_dir, long_dir = Path(short_dir), Path(long_dir)
    short_wavs = {p.relative_to(short_dir): p for p in short_dir.rglob("*.wav")} if short_dir.is_dir() else {}
    long_wavs = {p.relative_to(long_dir): p for p in long_dir.rglob("*.wav")} if long_dir.is_dir() else {}

    items = []
    for relpath in sorted(set(short_wavs) | set(long_wavs)):
        items.append(
            CorpusItem(
                id=_item_id(relpath),
                preset_relpath=str(relpath.with_suffix(".vital")),
                role=role_from_path(relpath),
                short_wav=str(short_wavs[relpath]) if relpath in short_wavs else None,
                long_wav=str(long_wavs[relpath]) if relpath in long_wavs else None,
            )
        )
    return items


def save_manifest(items: list[CorpusItem], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for item in items:
            fh.write(json.dumps(asdict(item)) + "\n")
    return path


def load_manifest(path: str | Path) -> list[CorpusItem]:
    items = []
    with Path(path).open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                items.append(CorpusItem(**json.loads(line)))
    return items


def role_counts(items: list[CorpusItem]) -> dict[str, int]:
    counts: dict[str, int] = {role: 0 for role in ROLES}
    for item in items:
        counts[item.role] = counts.get(item.role, 0) + 1
    return counts


def fit_feature_norm(items: list[CorpusItem]) -> NormStats:
    """Fit z-score stats over every rendered variant in the corpus — the
    "preset corpus" side of architecture.md's domain normalisation.
    """
    vectors = []
    for item in items:
        for wav in (item.short_wav, item.long_wav):
            if wav:
                vectors.append(features_from_file(wav))
    if not vectors:
        raise ValueError("no rendered wavs to fit normalisation stats from")
    return NormStats.fit(np.array(vectors))


def _item_vector(item: CorpusItem, embedder: Embedder) -> np.ndarray | None:
    vectors = [embedder.embed_file(wav) for wav in (item.short_wav, item.long_wav) if wav]
    if not vectors:
        return None
    return np.mean(vectors, axis=0)


def embed_manifest(items: list[CorpusItem], embedder: Embedder) -> tuple[list[str], np.ndarray]:
    """Returns (ids, matrix) for every item that has at least one rendered variant."""
    ids, vectors = [], []
    for item in items:
        vec = _item_vector(item, embedder)
        if vec is not None:
            ids.append(item.id)
            vectors.append(vec)
    if not vectors:
        return [], np.zeros((0, 0))
    return ids, np.stack(vectors)


def save_embeddings(ids: list[str], vectors: np.ndarray, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, ids=np.array(ids, dtype=object), vectors=vectors)
    return path


def load_embeddings(path: str | Path) -> tuple[list[str], np.ndarray]:
    data = np.load(path, allow_pickle=True)
    return list(data["ids"]), data["vectors"]


# ----------------------------------------------------------------------- cli

def cmd_manifest(args: argparse.Namespace) -> int:
    items = build_manifest(Path(args.short_dir), Path(args.long_dir))
    if not items:
        print("no wav files found under either directory", file=sys.stderr)
        return 1
    path = save_manifest(items, args.out)
    print(f"{len(items)} items -> {path}")
    print(f"roles: {role_counts(items)}")
    return 0


def cmd_embed(args: argparse.Namespace) -> int:
    items = load_manifest(args.manifest)
    if args.method == "random":
        embedder: Embedder = RandomEmbedder()
    elif args.method == "features":
        norm = fit_feature_norm(items)
        if args.out_norm:
            norm.save(args.out_norm)
        embedder = FeatureEmbedder(norm)
    elif args.method == "clap":
        try:
            from .embed import ClapEmbedder  # noqa: PLC0415

            embedder = ClapEmbedder()
        except ClapUnavailable as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    else:
        print(f"unknown method: {args.method}", file=sys.stderr)
        return 2

    ids, vectors = embed_manifest(items, embedder)
    save_embeddings(ids, vectors, args.out)
    print(f"embedded {len(ids)}/{len(items)} items ({args.method}) -> {args.out}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    items = load_manifest(args.manifest)
    print(f"{len(items)} items")
    for role, count in role_counts(items).items():
        print(f"  {role:<8} {count}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m voxfl.corpus",
        description="Build and embed the Phase 1 preset corpus, from wav trees "
        "already rendered by 'python -m voxfl.vital batch'.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("manifest", help="pair up short/long render trees into a corpus manifest")
    p.add_argument("short_dir", help="output dir of a short-hold 'voxfl.vital batch' run")
    p.add_argument("long_dir", help="output dir of a long-hold 'voxfl.vital batch' run")
    p.add_argument("-o", "--out", default="corpus/manifest.jsonl")
    p.set_defaults(func=cmd_manifest)

    p = sub.add_parser("embed", help="embed every manifest item with one baseline method")
    p.add_argument("manifest")
    p.add_argument("--method", choices=("random", "features", "clap"), required=True)
    p.add_argument("-o", "--out", default="corpus/embeddings.npz")
    p.add_argument("--out-norm", help="(features only) where to save the fitted NormStats")
    p.set_defaults(func=cmd_embed)

    p = sub.add_parser("stats", help="role counts for a corpus manifest")
    p.add_argument("manifest")
    p.set_defaults(func=cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
