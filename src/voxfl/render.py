"""Drive Vital headlessly through DawDreamer and render presets to audio.

Phase 0 tool #2. Its real job is to answer one question the whole corpus
build depends on: **how does a .vital preset get into a hosted plugin?**

DawDreamer can load ``.fxp`` and ``.vstpreset`` files, neither of which Vital
uses. So there are three candidate routes, and ``probe`` exists to find out
which of them actually work on your machine:

1. ``state``  — Vital's plugin state is very likely the preset JSON itself.
                If so, a state file can be rebuilt around any preset's JSON.
                Preserves everything. This is the hypothesis worth testing.
2. ``params`` — match preset JSON keys to host parameter names and set them
                one by one. Definitely works, but is **lossy**: wavetables,
                modulation routings and LFO shapes are not host parameters.
3. ``none``   — render whatever patch the plugin loaded with. Useful only to
                prove the rendering path itself works.
"""

from __future__ import annotations

import json
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .vitalfile import Preset

SAMPLE_RATE = 44100
BLOCK_SIZE = 512

# Keys that mark a blob as a Vital preset rather than arbitrary JSON.
VITAL_MARKERS = ("settings", "synth_version", "preset_name")


class RenderError(Exception):
    """Raised when the plugin cannot be loaded or rendered."""


def _require_dawdreamer():
    try:
        import dawdreamer  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RenderError(
            "dawdreamer is not installed. Run: pip install dawdreamer"
        ) from exc
    return dawdreamer


# --------------------------------------------------------------- state blob

@dataclass
class StateBlob:
    """A DawDreamer state file, split into a prefix and an embedded JSON body."""

    raw: bytes
    json_start: int | None
    json_end: int | None
    payload: dict[str, Any] | None

    @property
    def holds_vital_json(self) -> bool:
        return bool(self.payload) and any(k in self.payload for k in VITAL_MARKERS)

    @property
    def prefix(self) -> bytes:
        return self.raw[: self.json_start] if self.json_start is not None else b""

    @property
    def suffix(self) -> bytes:
        return self.raw[self.json_end :] if self.json_end is not None else b""

    def rebuild_with(self, preset: Preset) -> bytes:
        """Swap in a different preset's JSON, keeping any surrounding bytes."""
        if self.json_start is None:
            raise RenderError("this state file has no embedded JSON to replace")
        body = json.dumps(preset.data, separators=(",", ":")).encode("utf-8")
        return self.prefix + body + self.suffix


def parse_state(raw: bytes) -> StateBlob:
    """Find and parse a JSON object embedded anywhere in a state file."""
    start = raw.find(b"{")
    if start == -1:
        return StateBlob(raw, None, None, None)

    decoder = json.JSONDecoder()
    try:
        text = raw[start:].decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        # Trailing binary after the JSON is fine; decode leniently to locate it.
        text = raw[start:].decode("utf-8", errors="ignore")

    try:
        payload, consumed = decoder.raw_decode(text)
    except json.JSONDecodeError:
        return StateBlob(raw, None, None, None)

    if not isinstance(payload, dict):
        return StateBlob(raw, None, None, None)

    end = start + len(text[:consumed].encode("utf-8"))
    return StateBlob(raw, start, end, payload)


# ------------------------------------------------------------------- engine

class VitalHost:
    """A loaded Vital instance you can apply presets to and render from."""

    def __init__(self, plugin_path: str | Path, *, sample_rate: int = SAMPLE_RATE):
        daw = _require_dawdreamer()
        self.plugin_path = str(Path(plugin_path).resolve())
        if not Path(self.plugin_path).exists():
            raise RenderError(f"plugin not found: {self.plugin_path}")

        self.sample_rate = sample_rate
        self.engine = daw.RenderEngine(sample_rate, BLOCK_SIZE)
        try:
            self.synth = self.engine.make_plugin_processor("vital", self.plugin_path)
        except Exception as exc:  # noqa: BLE001 - dawdreamer raises bare RuntimeError
            raise RenderError(
                f"could not load plugin: {exc}\n"
                f"hint: on Windows the path is usually "
                f"C:\\Program Files\\Common Files\\VST3\\Vital.vst3"
            ) from exc
        self.engine.load_graph([(self.synth, [])])

    # ------------------------------------------------------------ params
    def parameters(self) -> list[dict[str, Any]]:
        return list(self.synth.get_parameters_description())

    def parameter_index(self) -> dict[str, int]:
        """Host parameter name (normalised) -> index."""
        index: dict[str, int] = {}
        for entry in self.parameters():
            name = entry.get("name")
            idx = entry.get("index")
            if isinstance(name, str) and isinstance(idx, int):
                index[_normalise(name)] = idx
        return index

    # ----------------------------------------------------------- presets
    def apply_state_file(self, path: str | Path) -> None:
        self.synth.load_state(str(Path(path).resolve()))

    def apply_params(self, preset: Preset) -> tuple[int, list[str]]:
        """Set host parameters from a preset's JSON. Returns (applied, missed)."""
        index = self.parameter_index()
        applied, missed = 0, []
        for key, value in preset.params().items():
            idx = index.get(_normalise(key))
            if idx is None:
                missed.append(key)
                continue
            if self.synth.set_parameter(idx, float(value)):
                applied += 1
            else:
                missed.append(key)
        return applied, missed

    def dump_state(self, path: str | Path) -> StateBlob:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.synth.save_state(str(path.resolve()))
        return parse_state(path.read_bytes())

    # ------------------------------------------------------------ render
    def render_note(
        self,
        *,
        note: int = 48,
        velocity: int = 100,
        hold: float = 1.5,
        tail: float = 1.0,
    ) -> np.ndarray:
        """Render one MIDI note. Returns a (channels, samples) float array."""
        self.synth.clear_midi()
        self.synth.add_midi_note(note, velocity, 0.0, hold)
        if not self.engine.render(hold + tail):
            raise RenderError("render() returned False")
        return np.asarray(self.engine.get_audio())


def _normalise(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def write_wav(path: str | Path, audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> Path:
    """Write a (channels, samples) float array as 16-bit PCM."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = np.atleast_2d(np.asarray(audio, dtype=np.float64))
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    if peak > 1.0:
        data = data / peak
    interleaved = data.T.reshape(-1)
    pcm = np.clip(interleaved * 32767.0, -32768, 32767).astype("<i2")

    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(data.shape[0])
        fh.setsampwidth(2)
        fh.setframerate(sample_rate)
        fh.writeframes(pcm.tobytes())
    return path


def audio_summary(audio: np.ndarray) -> dict[str, float]:
    """Enough to tell 'it made a sound' from 'it made silence' without ears."""
    data = np.asarray(audio, dtype=np.float64)
    if data.size == 0:
        return {"peak": 0.0, "rms": 0.0, "seconds": 0.0}
    mono = data.mean(axis=0) if data.ndim > 1 else data
    return {
        "peak": float(np.max(np.abs(data))),
        "rms": float(np.sqrt(np.mean(np.square(mono)))),
        "seconds": float(mono.shape[-1] / SAMPLE_RATE),
    }
