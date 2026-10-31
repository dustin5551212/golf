"""A decent, deterministic bot — good enough to reach every code path.

Deliberately the same policy the JavaScript suite uses, so a whole match takes the
same route here as it does there. Used by the test suites and by ``python -m golf``.
"""

from __future__ import annotations

from golf.engine import HAND, State, card_value

# A face-down card is worth this much when guessing: the midpoint of what it could be.
HIDDEN = 5.5


def column_value(hand: list[dict], i: int) -> float:
    other = i + 3 if i < 3 else i - 3
    value = lambda c: card_value(c["rank"]) if c["up"] else HIDDEN  # noqa: E731
    return value(hand[i]) + value(hand[other])


def best_gain(hand: list[dict], card: dict) -> dict:
    best = float("-inf")
    slot = 0
    for i in range(HAND):
        other = i + 3 if i < 3 else i - 3
        mate = card_value(hand[other]["rank"]) if hand[other]["up"] else HIDDEN
        gain = column_value(hand, i) - (card_value(card["rank"]) + mate)
        if gain > best:
            best = gain
            slot = i
    return {"gain": best, "slot": slot}


def choose_action(state: State, seat: int) -> dict | None:
    if state.phase == "done":
        return None if state.over else {"type": "next-hole"}
    hand = state.hands[seat]
    if state.phase == "draw":
        top = state.discard[-1] if state.discard else None
        # Swapping within the table never turns a card up, so a player who only ever
        # takes from the discard pile can keep a hole alive forever. Good players take
        # the discard when it is a clear win, and draw from the stock when they need to
        # expose their own face-down cards.
        if top and best_gain(hand, top)["gain"] >= 3:
            return {"type": "draw-discard"}
        return {"type": "draw-stock"}
    if state.phase == "swap":
        pending = state.pending
        assert pending is not None  # phase swap always holds a card
        gain, slot = best_gain(hand, pending)["gain"], best_gain(hand, pending)["slot"]
        if state.source == "stock" and gain <= 0:
            return {"type": "discard"}
        return {"type": "swap", "slot": slot}
    raise AssertionError(f"no action for phase {state.phase}")
