"""The redaction boundary. Everything a player is shown goes through here.

Python port of ``golf/src/view.mjs``.  This module is the only place that decides
what leaves the server, so "does the table leak?" is one file to read and one test
to run.

Golf hides two things: the face-down cards in every grid, including your own, and
the card currently in somebody's hand after a draw from the stock.

Rule of thumb: build the view from scratch, never by deleting fields off the engine
state.  A field added to the engine later should be invisible here until someone
deliberately exposes it.

The wire format stays camelCase (``turnsLeft``, ``discardTop``, ``holeScore``…)
because the unchanged browser client reads these keys.
"""

from __future__ import annotations

from .engine import HAND, State, legal_actions


def _hidden() -> dict:
    return {"hidden": True}


def _public_card(card: dict) -> dict:
    # Always face up: a card only reaches a view once it is public (played,
    # discarded, or held in the viewer's own hand), and the client should not have
    # to guess.
    return {"up": True, "rank": card["rank"], "suit": card["suit"]}


def _grid_for(hand: list[dict], seat: int) -> dict:
    """A face-down card keeps its position and nothing else. A face-up card is public
    to the whole table, which is what makes the game readable at a glance."""
    cards = []
    for card in hand[:HAND]:
        if card["up"]:
            cards.append({"up": True, **_public_card(card)})
        else:
            cards.append({"up": False, **_hidden()})
    return {"seat": seat, "cards": cards}


def view(state: State, seat: int, extra: dict | None = None) -> dict:
    is_turn = state.turn == seat
    hand = state.hands[seat] if seat < len(state.hands) else []

    out = {
        "you": seat,
        "hand": _grid_for(hand, seat),
        "others": [_grid_for(h, i) for i, h in enumerate(state.hands) if i != seat],
        "seats": [
            {
                "name": s["name"],
                "total": s["total"],
                "holeScore": state.hole_scores[i] if i < len(state.hole_scores) else None,
                "seat": i,
            }
            for i, s in enumerate(state.seats)
        ],
        "hole": state.hole,
        "holes": state.holes,
        "dealer": state.dealer,
        "turn": state.turn,
        "phase": state.phase,
        "ending": state.ending,
        "turnsLeft": state.turns_left,
        "over": state.over,
        # "knock" or "grid": the client holds the table open before showing totals.
        "endedBy": state.ended_by,
        # Counts and public piles only — never the stock's contents.
        # The stock is a count. The discard pile is face up on the table, so its
        # contents are public — players remember them anyway, and pretending
        # otherwise only makes the client lie about what the table looks like.
        "stock": len(state.stock),
        "discard": [_public_card(c) for c in state.discard],
        "discardTop": _public_card(state.discard[-1]) if state.discard else None,
        "discardCount": len(state.discard),
        # The drawn card is yours alone. Everyone else learns there is one, and
        # where it came from, and nothing more.
        "pending": _public_card(state.pending) if (is_turn and state.pending) else None,
        "holding": bool(is_turn and state.pending),
        "source": state.source if is_turn else None,
        "log": [{"text": e["text"], "hl": e["hl"], "hole": e["hole"]} for e in state.log],
        "legal": [dict(a) for a in legal_actions(state, seat)],
    }
    if extra:
        out.update(extra)
    return out


def view_for(state: State, seat: int, extra: dict | None = None) -> dict:
    """The same view with the seats filled in by the server (presence, names)."""
    return view(state, seat, extra)
