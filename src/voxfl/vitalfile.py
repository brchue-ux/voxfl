"""Read, inspect, modify and write Vital ``.vital`` preset files.

A ``.vital`` preset is JSON. This module deliberately makes **no assumptions
about Vital's schema** — it flattens whatever structure it finds into dotted
paths, so it keeps working if the schema differs from expectations or changes
between Vital versions. Phase 0 is about finding out what's in there, not
about asserting what should be.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

# Lists longer than this are summarised rather than flattened. Wavetable
# keyframe data runs to thousands of floats and would drown everything else.
BULK_LIST_THRESHOLD = 24

Scalar = str | int | float | bool | None


class VitalFileError(Exception):
    """Raised when a file cannot be read as a Vital preset."""


@dataclass
class Preset:
    """A parsed ``.vital`` preset."""

    data: dict[str, Any]
    path: Path | None = None
    was_gzipped: bool = False

    # ---------------------------------------------------------------- load
    @classmethod
    def load(cls, path: str | Path) -> "Preset":
        path = Path(path)
        raw = path.read_bytes()

        gzipped = raw[:2] == b"\x1f\x8b"
        if gzipped:
            try:
                raw = gzip.decompress(raw)
            except OSError as exc:  # pragma: no cover - corrupt input
                raise VitalFileError(f"{path.name}: gzip decompress failed: {exc}") from exc

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise VitalFileError(
                f"{path.name}: not UTF-8 text. If this is a .vitalbank or a "
                f"binary format, it is not supported yet."
            ) from exc

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise VitalFileError(
                f"{path.name}: not valid JSON at line {exc.lineno} col {exc.colno}. "
                f"Expected a Vital preset."
            ) from exc

        if not isinstance(data, dict):
            raise VitalFileError(f"{path.name}: JSON root is {type(data).__name__}, expected an object.")

        return cls(data=data, path=path, was_gzipped=gzipped)

    # ---------------------------------------------------------------- save
    def save(self, path: str | Path, *, compress: bool | None = None) -> Path:
        path = Path(path)
        text = json.dumps(self.data, separators=(",", ":"))
        payload = text.encode("utf-8")
        if compress if compress is not None else self.was_gzipped:
            payload = gzip.compress(payload)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    # ------------------------------------------------------------ metadata
    @property
    def name(self) -> str:
        return str(self.data.get("preset_name") or (self.path.stem if self.path else "?"))

    def meta(self) -> dict[str, Scalar]:
        """Top-level scalar fields — name, author, style, version and friends."""
        return {k: v for k, v in self.data.items() if _is_scalar(v)}

    # ------------------------------------------------------------ flatten
    def flatten(self, *, include_bulk: bool = False) -> dict[str, Scalar]:
        """Every scalar in the preset, keyed by dotted path.

        ``settings.filter_1_cutoff`` -> 0.62
        ``settings.lfos.0.name``     -> "Triangle"
        """
        return dict(_walk(self.data, "", include_bulk=include_bulk))

    def params(self) -> dict[str, float]:
        """Numeric knobs directly under ``settings`` — the tweakable surface."""
        settings = self.data.get("settings")
        if not isinstance(settings, dict):
            return {}
        return {
            k: float(v)
            for k, v in settings.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        }

    # -------------------------------------------------------- get and set
    def get(self, path: str) -> Any:
        node, key = self._resolve(path, create=False)
        if isinstance(node, list):
            return node[int(key)]
        if key not in node:
            raise KeyError(path)
        return node[key]

    def set(self, path: str, value: Any) -> Any:
        """Set a dotted path, returning the previous value."""
        node, key = self._resolve(path, create=False)
        if isinstance(node, list):
            idx = int(key)
            previous = node[idx]
            node[idx] = value
        else:
            if key not in node:
                raise KeyError(path)
            previous = node[key]
            node[key] = value
        return previous

    def nudge(self, path: str, delta: float) -> tuple[float, float]:
        """Add ``delta`` to a numeric path. Returns (before, after)."""
        before = self.get(path)
        if not isinstance(before, (int, float)) or isinstance(before, bool):
            raise TypeError(f"{path} is {type(before).__name__}, not a number")
        after = float(before) + delta
        self.set(path, after)
        return float(before), after

    def _resolve(self, path: str, *, create: bool) -> tuple[Any, str]:
        parts = path.split(".")
        node: Any = self.data
        for i, part in enumerate(parts[:-1]):
            trail = ".".join(parts[: i + 1])
            if isinstance(node, list):
                try:
                    node = node[int(part)]
                except (ValueError, IndexError) as exc:
                    raise KeyError(f"{trail}: no such index") from exc
            elif isinstance(node, dict):
                if part not in node:
                    if not create:
                        raise KeyError(f"{trail}: no such key")
                    node[part] = {}
                node = node[part]
            else:
                raise KeyError(f"{trail}: {type(node).__name__} is not traversable")
        return node, parts[-1]


# --------------------------------------------------------------------- diff

@dataclass
class Diff:
    changed: dict[str, tuple[Scalar, Scalar]]
    added: dict[str, Scalar]
    removed: dict[str, Scalar]

    def __bool__(self) -> bool:
        return bool(self.changed or self.added or self.removed)

    @property
    def total(self) -> int:
        return len(self.changed) + len(self.added) + len(self.removed)


def diff(a: Preset, b: Preset, *, include_bulk: bool = False) -> Diff:
    """Compare two presets scalar by scalar.

    This is the discovery tool for Phase 0: change one knob in Vital's GUI,
    save under a new name, diff the two files, and the parameter name that
    knob writes to falls straight out.
    """
    fa = a.flatten(include_bulk=include_bulk)
    fb = b.flatten(include_bulk=include_bulk)
    keys_a, keys_b = set(fa), set(fb)
    return Diff(
        changed={k: (fa[k], fb[k]) for k in keys_a & keys_b if fa[k] != fb[k]},
        added={k: fb[k] for k in keys_b - keys_a},
        removed={k: fa[k] for k in keys_a - keys_b},
    )


# ------------------------------------------------------------------ helpers

def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _walk(node: Any, prefix: str, *, include_bulk: bool) -> Iterator[tuple[str, Scalar]]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{prefix}.{key}" if prefix else str(key), include_bulk=include_bulk)
    elif isinstance(node, list):
        if not include_bulk and len(node) > BULK_LIST_THRESHOLD:
            yield (f"{prefix}[]", f"<{len(node)} items, omitted>")
            return
        for i, value in enumerate(node):
            yield from _walk(value, f"{prefix}.{i}", include_bulk=include_bulk)
    elif _is_scalar(node):
        yield (prefix, node)
