"""Golf — six-card, nine holes. The rules, with no UI and no network in it.

Python port of ``golf/src/engine.mjs``.  The whole game lives in a :class:`State`
so a server can hold it, redact it per player (``view.py``), and a test can play
ten thousand hands through it without a browser.  Every card the players are not
allowed to know stays in this object and is removed on the way out, never at the
source.

Naming: module-level ``apply`` keeps the source's name (it is not a Python
keyword, and keeping it makes a side-by-side diff readable).  Internal fields are
snake_case; the wire format in ``view.py`` is the source's camelCase because the
browser client reads it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = ["\u2660", "\u2665", "\u2666", "\u2663"]
COLS = [
    [0, 3],
    [1, 4],
    [2, 5],
]
HAND = 6
HOLES = 9
MIN_SEATS = 2
MAX_SEATS = 4


class RuleError(Exception):
    """An illegal move. The server turns this into a refusal; a test into a failure."""


def card_value(rank: str) -> int:
    """A 1, 2 minus two, K zero, face cards ten, everything else its own number."""
    if rank == "A":
        return 1
    if rank == "2":
        return -2
    if rank == "K":
        return 0
    if rank in ("J", "Q"):
        return 10
    return int(rank, 10)


def is_red(suit: str) -> bool:
    return suit == "\u2665" or suit == "\u2666"


def label(card: dict | None) -> str:
    return card["rank"] + card["suit"] if card else ""


def score_hand(hand: Sequence[dict]) -> dict:
    """A column of two equal ranks scores nothing — the whole point of the game."""
    total = 0
    cols = []
    for a, b in COLS:
        pair = hand[a]["rank"] == hand[b]["rank"]
        v = 0 if pair else card_value(hand[a]["rank"]) + card_value(hand[b]["rank"])
        cols.append({"v": v, "pair": pair})
        total += v
    return {"total": total, "cols": cols}


def build_deck() -> list[dict]:
    deck = []
    for suit in SUITS:
        for rank in RANKS:
            deck.append({"rank": rank, "suit": suit})
    return deck


def _imul32(a: int, b: int) -> int:
    """Math.imul: the low 32 bits of a two's-complement 32-bit multiply."""
    return (a * b) & 0xFFFFFFFF


def make_rng(seed: int | None = None) -> Callable[[], float]:
    """mulberry32 — small, fast, and seedable, so a failing test can be replayed.

    Bit-for-bit the same sequence as the JavaScript source (everything is kept in
    unsigned 32-bit arithmetic, which is how JS's int32 shifts behave).
    """
    a = (int(time.time() * 1000) if seed is None else int(seed)) & 0xFFFFFFFF

    def rng() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = a
        t = _imul32(t ^ (t >> 15), (t | 1) & 0xFFFFFFFF)
        t = (t ^ ((t + _imul32((t ^ (t >> 7)) & 0xFFFFFFFF, (t | 61) & 0xFFFFFFFF)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0

    return rng


def shuffle(deck: list[dict], rng: Callable[[], float]) -> list[dict]:
    for i in range(len(deck) - 1, 0, -1):
        j = int(rng() * (i + 1))
        deck[i], deck[j] = deck[j], deck[i]
    return deck


@dataclass
class State:
    seats: list[dict] = field(default_factory=list)
    hole: int = 1
    holes: int = HOLES
    dealer: int = 0
    turn: int = 0
    phase: str = "idle"
    stock: list[dict] = field(default_factory=list)
    discard: list[dict] = field(default_factory=list)
    hands: list[list[dict]] = field(default_factory=list)
    pending: dict | None = None
    source: str | None = None
    ending: bool = False
    turns_left: int = 0
    hole_scores: list = field(default_factory=list)
    log: list[dict] = field(default_factory=list)
    over: bool = False
    # A function does not survive JSON, so it is not part of the surface state.
    rng: Callable[[], float] | None = None


def _push_log(state: State, text: str, hl: bool = False) -> None:
    state.log.insert(0, {"text": text, "hl": bool(hl), "hole": state.hole})
    if len(state.log) > 6:
        state.log.pop()


def _start_hole(state: State) -> None:
    """Deal a hole. Two cards start face up — the outer corners of the grid — and
    the other four are the player's problem."""
    rng = state.rng
    assert rng is not None  # create_match always installs one
    state.stock = shuffle(build_deck(), rng)
    state.discard = []
    state.log = []
    state.hands = []
    for _ in state.seats:
        hand = []
        for _i in range(HAND):
            card = state.stock.pop()
            hand.append({"rank": card["rank"], "suit": card["suit"], "up": False})
        hand[0]["up"] = True
        hand[3]["up"] = True
        state.hands.append(hand)
    first = state.stock.pop()
    state.discard.append({"rank": first["rank"], "suit": first["suit"], "up": True})

    state.dealer = (state.dealer + 1) % len(state.seats)
    state.turn = (state.dealer + 1) % len(state.seats)
    state.phase = "draw"
    state.pending = None
    state.source = None
    state.ending = False
    state.turns_left = 0
    state.hole_scores = [None for _ in state.seats]


def create_match(seats: Any = None, holes: int = HOLES, seed: int | None = None) -> State:
    if isinstance(seats, (list, tuple)):
        count = len(seats)
        names = [
            s if isinstance(s, str) else (s.get("name") if isinstance(s, dict) else None) or f"Player {i + 1}"
            for i, s in enumerate(seats)
        ]
    else:
        count = int(seats or 0)
        names = [f"Player {i + 1}" for i in range(count)]
    if count < MIN_SEATS or count > MAX_SEATS:
        raise RuleError(f"golf needs {MIN_SEATS} to {MAX_SEATS} players, got {count}")

    state = State(
        seats=[{"name": name, "total": 0} for name in names],
        hole=1,
        holes=holes,
        dealer=count - 1,
        turn=0,
        phase="idle",
        rng=make_rng(seed),
    )
    _start_hole(state)
    _push_log(state, f"{state.seats[state.turn]['name']} tees off on hole 1", True)
    return state


# ── the moves ───────────────────────────────────────────────────────────


def _draw_stock(state: State) -> None:
    if not state.stock:
        # The stock cannot run out in a normal hole (4 players × 6 = 24 of 52), but a
        # recycled pile beats a dead game if it ever does.
        rng = state.rng
        assert rng is not None
        top = state.discard.pop()
        state.stock = shuffle(
            [{"rank": c["rank"], "suit": c["suit"]} for c in state.discard],
            rng,
        )
        state.discard = [top]
    card = state.stock.pop()
    state.pending = {"rank": card["rank"], "suit": card["suit"]}
    state.source = "stock"
    state.phase = "swap"


def _draw_discard(state: State) -> None:
    if not state.discard:
        raise RuleError("the discard pile is empty")
    card = state.discard.pop()
    state.pending = {"rank": card["rank"], "suit": card["suit"]}
    state.source = "discard"
    state.phase = "swap"


def _swap_into(state: State, slot: Any) -> None:
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0 or slot >= HAND:
        raise RuleError(f"no such slot: {slot}")
    pending = state.pending
    assert pending is not None
    hand = state.hands[state.turn]
    taken = hand[slot]
    hand[slot] = {"rank": pending["rank"], "suit": pending["suit"], "up": True}
    state.discard.append({"rank": taken["rank"], "suit": taken["suit"], "up": True})
    _push_log(
        state,
        f"{state.seats[state.turn]['name']} took {label(pending)} for "
        f"{label(taken) if taken['up'] else 'a face-down card'}",
        True,
    )
    state.pending = None
    state.source = None
    _end_turn(state)


def _discard_drawn(state: State) -> None:
    """Throwing away the drawn card is a pass: the turn moves on and none of your
    face-down cards is turned up.

    (House rule. The published versions of six-card Golf make you expose a card for
    this, which is what stops a table from passing forever; here a grid only fills
    when somebody swaps into a slot they cannot see.)
    """
    state.discard.append({"rank": state.pending["rank"], "suit": state.pending["suit"], "up": True})
    _push_log(state, f"{state.seats[state.turn]['name']} threw {label(state.pending)} away")
    state.pending = None
    state.source = None
    _end_turn(state)


def _score_hole(state: State) -> None:
    state.phase = "done"
    state.pending = None
    state.source = None
    scores = []
    for i, hand in enumerate(state.hands):
        for c in hand:
            c["up"] = True
        total = score_hand(hand)["total"]
        state.seats[i]["total"] += total
        scores.append(total)
    state.hole_scores = scores
    state.over = state.hole >= state.holes
    low = min(state.hole_scores)
    who = [s["name"] for i, s in enumerate(state.seats) if state.hole_scores[i] == low]
    _push_log(state, f"hole {state.hole}: {' & '.join(who)} lowest at {low}", True)


def _end_turn(state: State) -> None:
    """Every other player gets one more turn once someone is out."""
    hand = state.hands[state.turn]
    all_up = all(c["up"] for c in hand)
    if not state.ending and all_up:
        state.ending = True
        state.turns_left = len(state.seats) - 1
        _push_log(state, f"{state.seats[state.turn]['name']} is out — one last turn each", True)
    elif state.ending:
        state.turns_left -= 1
    if state.ending and state.turns_left <= 0:
        _score_hole(state)
        return
    state.turn = (state.turn + 1) % len(state.seats)
    state.phase = "draw"
    state.pending = None
    state.source = None


def apply(state: State, seat: Any, action: Any) -> State:
    """Apply one action for one seat.

    Raises :class:`RuleError` on anything illegal — the server turns that into a
    refusal, a test turns it into a failure.
    """
    if not isinstance(action, dict) or not isinstance(action.get("type"), str):
        raise RuleError("no action")
    if isinstance(seat, bool) or not isinstance(seat, int) or seat < 0 or seat >= len(state.seats):
        raise RuleError("no such seat")

    # Between holes anyone at the table may move the game on; there is no host.
    if action["type"] == "next-hole":
        if state.phase != "done":
            raise RuleError("the hole is still being played")
        if state.over:
            raise RuleError("the match is over")
        state.hole += 1
        _start_hole(state)
        _push_log(state, f"{state.seats[state.turn]['name']} tees off on hole {state.hole}", True)
        return state

    if state.phase == "done":
        raise RuleError("the hole is over")
    if state.turn != seat:
        raise RuleError("it is not your turn")

    kind = action["type"]
    if kind == "draw-stock":
        if state.phase != "draw":
            raise RuleError("you cannot draw now")
        _draw_stock(state)
    elif kind == "draw-discard":
        if state.phase != "draw":
            raise RuleError("you cannot draw now")
        _draw_discard(state)
    elif kind == "swap":
        if state.phase != "swap":
            raise RuleError("nothing to place")
        _swap_into(state, action.get("slot"))
    elif kind == "discard":
        if state.phase != "swap":
            raise RuleError("nothing to throw away")
        if state.source != "stock":
            raise RuleError("a card taken from the discard pile must be placed")
        _discard_drawn(state)
    else:
        raise RuleError(f"unknown action: {kind}")
    return state


def legal_actions(state: State, seat: int) -> list[dict]:
    """What the current player may legally do — the client mirrors this to enable UI."""
    if state.phase == "done":
        return [] if state.over else [{"type": "next-hole"}]
    if state.turn != seat:
        return []
    if state.phase == "draw":
        return [{"type": "draw-stock"}, {"type": "draw-discard"}]
    if state.phase == "swap":
        slots = [{"type": "swap", "slot": i} for i in range(HAND)]
        if state.source == "stock":
            slots.append({"type": "discard"})
        return slots
    return []
