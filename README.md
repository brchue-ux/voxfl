# voxfl

Hum an idea, get editable notes in FL Studio.

A Windows desktop tool that records a short vocal take — humming, singing,
later beatboxing — and turns it into a musically-corrected MIDI pattern you can
drop straight into FL Studio and keep working on.

## Status

Design locked, not yet built. Phase 0 (the end-to-end spike) is the next step.

## Decisions made

| Question | Answer |
| --- | --- |
| Target DAW | FL Studio |
| Platform | Windows |
| First capability | Humming → melody |
| Interaction model | Record a take, then convert (not live/real-time) |
| How notes reach FL | MIDI file first, virtual MIDI port second, FL piano-roll script last |

The README previously called "how software actually gets musical content into
FL Studio" the central open question. It is answered in
[docs/architecture.md](docs/architecture.md#getting-notes-into-fl-studio) —
there are three viable routes, ranked by risk, and the lowest-risk one is a
plain `.mid` file. Phase 0 exists to prove it in a day.

## What this is not

Not a real-time voice instrument (that's [Dubler 2](https://vochlea.com/products/dubler2)).
Not a song generator. It is a **capture tool**: the fastest path from a
melody in your head to notes on a grid you can edit.

## Docs

- [Roadmap](docs/ROADMAP.md) — phases, exit criteria, sizing, risks
- [Architecture](docs/architecture.md) — stack, pipeline, FL integration routes
- [Decisions](docs/decisions.md) — decision log and competitive positioning
- [Evaluation](docs/evaluation.md) — how we know it is actually getting better
