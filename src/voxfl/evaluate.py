"""``python -m voxfl.evaluate`` — run the baselines against the benchmark and
report Recall@1/5/20 and MRR, per role and overall.

[evaluation.md](../../docs/evaluation.md#baselines-in-order): random within
role, hand-crafted features, CLAP — each measured with and without role
filtering so the filtering win is visible on its own, not baked in silently.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .benchmark import BenchmarkEntry, load_manifest as load_benchmark, ready_entries
from .corpus import (
    CorpusItem,
    NormStats,
    fit_feature_norm,
    load_embeddings,
    load_manifest as load_corpus,
    save_embeddings,
)
from .embed import ClapUnavailable, Embedder, FeatureEmbedder
from .features import features_from_file
from .retrieval import RetrievalIndex

RECALL_KS = (1, 5, 20)


@dataclass
class QueryResult:
    entry_id: str
    role: str
    rank: int | None  # 1-based rank of the true target among candidates, or None if not found


def _aggregate(results: list["QueryResult"]) -> dict | None:
    if not results:
        return None
    n = len(results)
    recalls = {k: sum(1 for r in results if r.rank is not None and r.rank <= k) / n for k in RECALL_KS}
    mrr = sum((1.0 / r.rank) if r.rank else 0.0 for r in results) / n
    return {"n": n, **{f"recall@{k}": v for k, v in recalls.items()}, "mrr": mrr}


def summarize(results: list[QueryResult]) -> dict:
    roles = sorted({r.role for r in results})
    return {
        "overall": _aggregate(results),
        "by_role": {role: _aggregate([r for r in results if r.role == role]) for role in roles},
    }


def run_baseline(
    entries: list[BenchmarkEntry],
    index: RetrievalIndex,
    *,
    query_embedder: Embedder | None,
    role_filter: bool,
    seed: int = 0,
) -> list[QueryResult]:
    """query_embedder=None is the random baseline: retrieval.RetrievalIndex.rank
    shuffles the candidate set instead of ranking by similarity."""
    rng = np.random.default_rng(seed)
    results = []
    for e in ready_entries(entries):
        query = query_embedder.embed_file(e.imitation_wav) if query_embedder else None
        ranked = index.rank(query, role=e.role if role_filter else None, rng=rng)
        rank = (ranked.index(e.id) + 1) if e.id in ranked else None
        results.append(QueryResult(entry_id=e.id, role=e.role, rank=rank))
    return results


def build_index(corpus_items: list[CorpusItem], ids: list[str], vectors: np.ndarray | None) -> RetrievalIndex:
    roles = {item.id: item.role for item in corpus_items}
    if vectors is None:
        return RetrievalIndex(ids=[item.id for item in corpus_items], roles=roles, vectors=None)
    return RetrievalIndex(ids=ids, roles=roles, vectors=vectors)


def features_query_norm(entries: list[BenchmarkEntry]) -> NormStats:
    """z-score stats fit on the vocal-query corpus — architecture.md's other
    half of domain normalisation. Only the benchmark's own imitations are
    available as "a corpus of vocal queries", which is the honest limitation
    to note: with ~50 recordings this is a rough estimate, not a stable
    population statistic, and will sharpen once Phase 3 accumulates more.
    """
    vectors = [features_from_file(e.imitation_wav) for e in ready_entries(entries)]
    return NormStats.fit(np.array(vectors))


def _print_table(name: str, report: dict) -> None:
    overall = report["overall"]
    if overall is None:
        print(f"{name}: no ready benchmark entries")
        return
    header = f"{'role':<8} n    R@1    R@5    R@20   MRR"
    print(f"\n== {name} ==")
    print(header)
    print(f"{'overall':<8} {overall['n']:<4} " + _row(overall))
    for role, stats in sorted(report["by_role"].items()):
        if stats:
            print(f"{role:<8} {stats['n']:<4} " + _row(stats))


def _row(stats: dict) -> str:
    return (
        f"{stats['recall@1']:.3f}  {stats['recall@5']:.3f}  "
        f"{stats['recall@20']:.3f}  {stats['mrr']:.3f}"
    )


def cmd_run(args: argparse.Namespace) -> int:
    corpus_items = load_corpus(args.corpus_manifest)
    entries = load_benchmark(args.benchmark_manifest)
    ready = ready_entries(entries)
    if not ready:
        print("no benchmark entries have an ingested recording yet — run "
              "'voxfl.benchmark ingest' first", file=sys.stderr)
        return 1
    print(f"{len(ready)}/{len(entries)} benchmark entries ready "
          f"({len(corpus_items)} corpus items)")

    report: dict = {}

    # Baseline 1: random within role.
    random_index = build_index(corpus_items, [], None)
    for filt in (False, True):
        label = f"random{'+role' if filt else ''}"
        results = run_baseline(entries, random_index, query_embedder=None, role_filter=filt, seed=args.seed)
        report[label] = summarize(results)
        _print_table(label, report[label])

    # Baseline 2: hand-crafted timbral features, domain-normalised.
    preset_norm = fit_feature_norm(corpus_items)
    query_norm = features_query_norm(entries)
    preset_embedder = FeatureEmbedder(preset_norm)
    query_embedder = FeatureEmbedder(query_norm)

    from .corpus import embed_manifest  # noqa: PLC0415

    ids, vectors = embed_manifest(corpus_items, preset_embedder)
    if args.save_embeddings:
        save_embeddings(ids, vectors, Path(args.save_embeddings) / "features.npz")
    feature_index = build_index(corpus_items, ids, vectors)
    for filt in (False, True):
        label = f"features{'+role' if filt else ''}"
        results = run_baseline(entries, feature_index, query_embedder=query_embedder, role_filter=filt, seed=args.seed)
        report[label] = summarize(results)
        _print_table(label, report[label])

    # Baseline 3: CLAP, optional — needs transformers+torch and a model download.
    if args.skip_clap:
        report["clap"] = {"skipped": "requested with --skip-clap"}
    else:
        try:
            from .embed import ClapEmbedder  # noqa: PLC0415

            clap = ClapEmbedder()
            ids, vectors = embed_manifest(corpus_items, clap)
            if args.save_embeddings:
                save_embeddings(ids, vectors, Path(args.save_embeddings) / "clap.npz")
            clap_index = build_index(corpus_items, ids, vectors)
            for filt in (False, True):
                label = f"clap{'+role' if filt else ''}"
                results = run_baseline(entries, clap_index, query_embedder=clap, role_filter=filt, seed=args.seed)
                report[label] = summarize(results)
                _print_table(label, report[label])
        except ClapUnavailable as exc:
            report["clap"] = {"skipped": str(exc)}
            print(f"\n== clap ==\nskipped: {exc}")

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2))
        print(f"\nwrote {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m voxfl.evaluate",
        description="Run Phase 1 baselines against the personal benchmark.",
    )
    p = parser.add_argument
    p("corpus_manifest", help="corpus manifest.jsonl from voxfl.corpus")
    p("benchmark_manifest", help="benchmark manifest.jsonl from voxfl.benchmark (after ingest)")
    p("-o", "--out", help="write the full JSON report here")
    p("--save-embeddings", help="directory to also write each baseline's corpus embeddings to")
    p("--skip-clap", action="store_true", help="skip the CLAP baseline (no transformers/torch needed)")
    p("--seed", type=int, default=0)
    parser.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
