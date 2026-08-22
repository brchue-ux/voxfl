from pathlib import Path

import numpy as np
import pytest

from voxfl.benchmark import (
    BenchmarkEntry,
    ingest,
    load_manifest,
    ready_entries,
    save_manifest,
    scaffold,
    write_checklist,
)
from voxfl.corpus import CorpusItem
from voxfl.render import write_wav

SR = 22050


def _tone_wav(path: Path, freq=220.0, duration=0.3):
    t = np.arange(int(duration * SR)) / SR
    write_wav(path, np.sin(2 * np.pi * freq * t)[None, :], SR)


def _corpus_items(n_per_role=4):
    items = []
    for role in ("bass", "lead", "pad", "pluck"):
        for i in range(n_per_role):
            items.append(
                CorpusItem(
                    id=f"{role}__{i}",
                    preset_relpath=f"{role}/{i}.vital",
                    role=role,
                    short_wav=f"{role}/{i}_short.wav",
                    long_wav=f"{role}/{i}_long.wav",
                )
            )
    return items


def test_scaffold_is_stratified_across_roles():
    entries = scaffold(_corpus_items(n_per_role=10), n_total=40, seed=0)
    roles = {e.role for e in entries}
    assert roles == {"bass", "lead", "pad", "pluck"}
    counts = {r: sum(1 for e in entries if e.role == r) for r in roles}
    assert all(c == 10 for c in counts.values())  # 40 // 4 == 10 each


def test_scaffold_never_exceeds_available_pool():
    entries = scaffold(_corpus_items(n_per_role=2), n_total=100, seed=0)
    assert sum(1 for e in entries if e.role == "bass") == 2


def test_scaffold_skips_roles_with_no_items():
    entries = scaffold(_corpus_items(n_per_role=3), n_total=20, roles=("bass", "orchestral"), seed=0)
    assert {e.role for e in entries} == {"bass"}


def test_write_checklist_lists_every_entry(tmp_path):
    entries = scaffold(_corpus_items(n_per_role=2), n_total=8, seed=0)
    path = write_checklist(entries, tmp_path / "TODO.md")
    text = path.read_text()
    for e in entries:
        assert e.id in text


def test_manifest_save_load_round_trip(tmp_path):
    entries = [BenchmarkEntry(id="a", preset_relpath="Bass/a.vital", role="bass", preset_wav="a.wav")]
    path = save_manifest(entries, tmp_path / "manifest.jsonl")
    assert load_manifest(path) == entries


class TestIngest:
    def test_fills_in_matching_recordings(self, tmp_path):
        recordings = tmp_path / "recordings"
        _tone_wav(recordings / "a.wav")
        entries = [BenchmarkEntry(id="a", preset_relpath="x", role="bass", preset_wav="p.wav")]

        updated, missing, invalid = ingest(entries, recordings)
        assert missing == []
        assert invalid == []
        assert updated[0].imitation_wav == str(recordings / "a.wav")

    def test_reports_missing_recordings(self, tmp_path):
        entries = [BenchmarkEntry(id="a", preset_relpath="x", role="bass", preset_wav="p.wav")]
        updated, missing, invalid = ingest(entries, tmp_path / "recordings")
        assert missing == ["a"]
        assert updated[0].imitation_wav is None

    def test_rejects_silent_recording(self, tmp_path):
        recordings = tmp_path / "recordings"
        write_wav(recordings / "a.wav", np.zeros((1, SR // 2)), SR)
        entries = [BenchmarkEntry(id="a", preset_relpath="x", role="bass", preset_wav="p.wav")]

        updated, missing, invalid = ingest(entries, recordings)
        assert missing == []
        assert len(invalid) == 1
        assert "silent" in invalid[0]
        assert updated[0].imitation_wav is None

    def test_rejects_too_short_recording(self, tmp_path):
        recordings = tmp_path / "recordings"
        t = np.arange(int(0.05 * SR)) / SR  # 50ms, below the 0.2s floor
        write_wav(recordings / "a.wav", np.sin(2 * np.pi * 220 * t)[None, :], SR)
        entries = [BenchmarkEntry(id="a", preset_relpath="x", role="bass", preset_wav="p.wav")]

        _, missing, invalid = ingest(entries, recordings)
        assert missing == []
        assert len(invalid) == 1
        assert "short" in invalid[0]


def test_ready_entries_filters_on_imitation_wav():
    entries = [
        BenchmarkEntry(id="a", preset_relpath="x", role="bass", preset_wav="p", imitation_wav="i.wav"),
        BenchmarkEntry(id="b", preset_relpath="y", role="bass", preset_wav="p", imitation_wav=None),
    ]
    assert [e.id for e in ready_entries(entries)] == ["a"]
