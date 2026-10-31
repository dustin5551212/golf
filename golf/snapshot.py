"""A canonical, JSON-safe snapshot of an engine state, for parity testing.

Mirrors ``snapshot()`` in ``tools/dump_parity.mjs`` exactly. Two things are
deliberately included that a casual summary would leave out: the *order* of the
stock (deck consumption is where a port drifts) and the legal actions of every
seat, not just the one to move.
"""

from __future__ import annotations

from .engine import State, legal_actions


def _label(card: dict | None) -> str | None:
    return card["rank"] + card["suit"] if card else None


def snapshot(state: State) -> dict:
    return {
        "hole": state.hole,
        "holes": state.holes,
        "dealer": state.dealer,
        "turn": state.turn,
        "phase": state.phase,
        "ending": state.ending,
        "turnsLeft": state.turns_left,
        "over": state.over,
        "seats": [{"name": s["name"], "total": s["total"]} for s in state.seats],
        "holeScores": list(state.hole_scores),
        "hands": [[{"rank": c["rank"], "suit": c["suit"], "up": c["up"]} for c in hand] for hand in state.hands],
        "stock": [c["rank"] + c["suit"] for c in state.stock],
        "discard": [c["rank"] + c["suit"] for c in state.discard],
        "pending": _label(state.pending),
        "source": state.source,
        "log": [{"text": e["text"], "hl": e["hl"], "hole": e["hole"]} for e in state.log],
        "legal": [legal_actions(state, i) for i in range(len(state.seats))],
    }
