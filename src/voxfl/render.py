"""Drive Vital headlessly through DawDreamer and render presets to audio.

Phase 0 tool #2. Its real job is to answer one question the whole corpus
build depends on: **how does a .vital preset get into a hosted plugin?**

DawDreamer can load ``.fxp`` and ``.vstpreset`` files, neither of which Vital
uses. So there are three candidate routes, and ``probe`` exists to find out
which of them actually work on your machine:

1. ``state``  — Vital's plugin state *is* the preset JSON — confirmed at
                Vital's own source (``SynthPlugin::getStateInformation``).
                DawDreamer's save_state/load_state pass VST3 host-state bytes
                straight through, so what actually reaches Python is JUCE's
                own generic VST3 host-state wrapper around that JSON (see
                ``parse_state`` below), not the JSON itself. Once unwrapped,
                a state file can be rebuilt around any preset's JSON and
                preserves everything: wavetables, modulation routing, LFO
                shapes.
2. ``params`` — match preset JSON keys to host parameter names and set them
                one by one. Definitely works, but is **lossy**: wavetables,
                modulation routings and LFO shapes are not host parameters.
3. ``none``   — render whatever patch the plugin loaded with. Useful only to
                prove the rendering path itself works.
"""

from __future__ import annotations

import json
import re
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


# --------------------------------------------------------- JUCE VST3 wrapper
#
# DawDreamer's save_state/load_state/get_state/set_state pass VST3 "host
# state" bytes straight through to/from the plugin, unmodified (DawDreamer's
# PluginProcessor::loadStateInformation/saveStateInformation call
# AudioPluginInstance::setStateInformation/getStateInformation directly).
# That state is JUCE's own generic VST3 host-state format, not Vital's raw
# plugin state:
#
#   "VC2!" magic (4 bytes) + XML length (4 bytes, little-endian)
#   + XML text: <VST3PluginState><IComponent>...</IComponent>
#               <IEditController>...</IEditController></VST3PluginState>
#   + one trailing NUL byte
#
# (AudioProcessor::copyXmlToBinary/getXmlFromBinary — magic 0x21324356 LE is
# the bytes "VC2!"). The <IComponent> element's text is Vital's JSON preset
# (plus a trailing NUL), base64-encoded with JUCE's own nonstandard alphabet
# and LSB-first bit packing (MemoryBlock::toBase64Encoding/fromBase64Encoding)
# — not RFC 4648. <IComponent> is what drives the audio engine;
# <IEditController> is just a parameter mirror JUCE resets from <IComponent>
# on load, so it can be carried through unmodified.

VC2_MAGIC = b"VC2!"

# Index 0 is '.', index 63 is '+' — no '/', no '=' padding.
_JUCE_B64_ALPHABET = ".ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+"
_JUCE_B64_DECODE = {ch: i for i, ch in enumerate(_JUCE_B64_ALPHABET)}

_ICOMPONENT_RE = re.compile(r"<IComponent>(.*?)</IComponent>", re.DOTALL)


def _get_bit_range(data: bytes, bit_start: int, num_bits: int) -> int:
    """Port of JUCE's MemoryBlock::getBitRange (LSB-first bit extraction)."""
    res = 0
    byte, offset, bits_so_far, size = bit_start >> 3, bit_start & 7, 0, len(data)
    while num_bits > 0 and byte < size:
        bits_this_time = min(num_bits, 8 - offset)
        mask = (0xFF >> (8 - bits_this_time)) << offset
        res |= ((data[byte] & mask) >> offset) << bits_so_far
        bits_so_far += bits_this_time
        num_bits -= bits_this_time
        byte += 1
        offset = 0
    return res


def _set_bit_range(buf: bytearray, bit_start: int, num_bits: int, value: int) -> None:
    """Port of JUCE's MemoryBlock::setBitRange (LSB-first bit packing)."""
    byte, offset = bit_start >> 3, bit_start & 7
    size = len(buf)
    while num_bits > 0 and byte < size:
        bits_this_time = min(num_bits, 8 - offset)
        local_mask = ((1 << bits_this_time) - 1) << offset
        bits = (value & ((1 << bits_this_time) - 1)) << offset
        buf[byte] = (buf[byte] & (~local_mask & 0xFF)) | bits
        value >>= bits_this_time
        num_bits -= bits_this_time
        byte += 1
        offset = 0


def juce_base64_encode(data: bytes) -> str:
    """JUCE's MemoryBlock::toBase64Encoding: nonstandard alphabet, LSB-first
    6-bit packing, and a "<decoded-byte-count>." length prefix."""
    num_chars = (len(data) * 8 + 5) // 6
    chars = (_JUCE_B64_ALPHABET[_get_bit_range(data, i * 6, 6)] for i in range(num_chars))
    return f"{len(data)}.{''.join(chars)}"


def juce_base64_decode(encoded: str) -> bytes:
    """Inverse of juce_base64_encode (JUCE's MemoryBlock::fromBase64Encoding).

    Matches JUCE's behaviour of silently skipping characters outside the
    alphabet rather than erroring — never triggered by real Vital data, since
    the alphabet contains none of XML's reserved characters.
    """
    dot = encoded.find(".")
    if dot == -1:
        raise RenderError("not JUCE base64: missing '<len>.' length prefix")
    size = int(encoded[:dot])
    buf = bytearray(size)
    pos = 0
    for ch in encoded[dot + 1 :]:
        value = _JUCE_B64_DECODE.get(ch)
        if value is None:
            continue
        _set_bit_range(buf, pos * 6, 6, value)
        pos += 1
    return bytes(buf)


def _unwrap_vst3_state(raw: bytes) -> str | None:
    """Verify the VC2! magic + length header and return the XML text."""
    if raw[:4] != VC2_MAGIC or len(raw) < 8:
        return None
    xml_length = int.from_bytes(raw[4:8], "little")
    xml_bytes = raw[8 : 8 + xml_length]
    if len(xml_bytes) != xml_length:
        return None
    try:
        return xml_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _wrap_vst3_state(xml: str) -> bytes:
    """Inverse of _unwrap_vst3_state: rebuild the VC2! magic+length+XML+NUL frame."""
    xml_bytes = xml.encode("utf-8")
    return VC2_MAGIC + len(xml_bytes).to_bytes(4, "little") + xml_bytes + b"\x00"


# --------------------------------------------------------------- state blob

@dataclass
class StateBlob:
    """A DawDreamer state file: JUCE's VST3 host-state wrapper (VC2! + XML +
    IComponent base64) around Vital's JSON plugin state — or, as a fallback
    for state blobs that are not VST3-wrapped, bare JSON found in the bytes.
    """

    raw: bytes
    xml: str | None = None
    payload: dict[str, Any] | None = None
    json_start: int | None = None
    json_end: int | None = None

    @property
    def holds_vital_json(self) -> bool:
        return bool(self.payload) and any(k in self.payload for k in VITAL_MARKERS)

    @property
    def injectable(self) -> bool:
        """Whether rebuild_with() has somewhere to splice a new preset's JSON."""
        if self.xml is not None:
            return _ICOMPONENT_RE.search(self.xml) is not None
        return self.json_start is not None

    @property
    def prefix(self) -> bytes:
        return self.raw[: self.json_start] if self.json_start is not None else b""

    @property
    def suffix(self) -> bytes:
        return self.raw[self.json_end :] if self.json_end is not None else b""

    def rebuild_with(self, preset: Preset) -> bytes:
        """Swap in a different preset's JSON, keeping everything else — the
        IEditController block, XML formatting, VC2! frame — as captured."""
        if self.xml is not None:
            match = _ICOMPONENT_RE.search(self.xml)
            if match is None:
                raise RenderError("this state file's XML has no <IComponent> element to replace")
            body = json.dumps(preset.data, separators=(",", ":")).encode("utf-8") + b"\x00"
            new_b64 = juce_base64_encode(body)
            new_xml = self.xml[: match.start(1)] + new_b64 + self.xml[match.end(1) :]
            return _wrap_vst3_state(new_xml)
        if self.json_start is None:
            raise RenderError("this state file has no embedded JSON to replace")
        body = json.dumps(preset.data, separators=(",", ":")).encode("utf-8")
        return self.prefix + body + self.suffix


def parse_state(raw: bytes) -> StateBlob:
    """Recover Vital's preset JSON from a DawDreamer state dump.

    Peels back JUCE's VST3 host-state wrapper (VC2! magic + XML + IComponent
    base64 — see module notes above) first, since that's the real shape of
    every DawDreamer state dump for a JUCE VST3 plugin. Falls back to a bare
    ``{`` scan for state blobs that turn out not to be VST3-wrapped.
    """
    xml = _unwrap_vst3_state(raw)
    if xml is not None:
        match = _ICOMPONENT_RE.search(xml)
        if match is None:
            return StateBlob(raw, xml=xml)
        payload = None
        try:
            decoded = juce_base64_decode(match.group(1))
        except RenderError:
            decoded = None
        if decoded is not None:
            body = decoded[:-1] if decoded.endswith(b"\x00") else decoded
            try:
                candidate = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                candidate = None
            if isinstance(candidate, dict):
                payload = candidate
        return StateBlob(raw, xml=xml, payload=payload)

    return _parse_bare_json(raw)


def _parse_bare_json(raw: bytes) -> StateBlob:
    """Legacy fallback: find and parse a JSON object embedded anywhere in a
    non-VST3-wrapped blob."""
    start = raw.find(b"{")
    if start == -1:
        return StateBlob(raw)

    decoder = json.JSONDecoder()
    try:
        text = raw[start:].decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        # Trailing binary after the JSON is fine; decode leniently to locate it.
        text = raw[start:].decode("utf-8", errors="ignore")

    try:
        payload, consumed = decoder.raw_decode(text)
    except json.JSONDecodeError:
        return StateBlob(raw)

    if not isinstance(payload, dict):
        return StateBlob(raw)

    end = start + len(text[:consumed].encode("utf-8"))
    return StateBlob(raw, json_start=start, json_end=end, payload=payload)


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
