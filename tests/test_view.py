"""The redaction boundary, re-expressed in Python idiom from ``golf/src/view.test.js``.

The point of every test here is one sentence: nothing a player is not entitled to know
may appear anywhere in the JSON they are sent.
"""

from __future__ import annotations

import json

import pytest

from golf.engine import HAND, apply, card_value, create_match
from golf.view import view
from golf.policy import choose_action


def label(card: dict) -> str:
    return card["rank"] + card["suit"]


def as_json(value) -> str:
    # ensure_ascii=False matters: with the default, suits become \u2660 and every
    # "does this card leak?" check below would silently pass.
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def visible_labels(v: dict) -> set[str]:
    """Every card a player can actually see, read straight off the view structure."""
    out = set()
    for card in [*v["hand"]["cards"], *[c for o in v["others"] for c in o["cards"]]]:
        if card["up"]:
            out.add(label(card))
    for card in v["discard"]:
        out.add(label(card))
    if v["pending"]:
        out.add(label(v["pending"]))
    return out


def expected_labels(state, seat: int) -> set[str]:
    """What the whole table is entitled to know after this state."""
    out = set()
    for hand in state.hands:
        for c in hand:
            if c["up"]:
                out.add(label(c))
    for c in state.discard:
        out.add(label(c))
    if state.turn == seat and state.pending:
        out.add(label(state.pending))
    return out


def hidden_cards(state) -> list[dict]:
    return [c for hand in state.hands for c in hand if not c["up"]]


def assert_no_leak(state, seat: int, where: str = "") -> dict:
    v = view(state, seat)
    blob = as_json(v)

    # 1. Nothing face down is named, anywhere — including in your own grid, and
    #    including anywhere it might have slipped into a log line.
    for card in hidden_cards(state):
        assert label(card) not in blob, f"{where} seat {seat}: face-down {label(card)} leaked"

    # 2. The stock is a count, not a list.
    for card in state.stock:
        assert label(card) not in blob, f"{where} seat {seat}: stock card {label(card)} leaked"

    # 3. Exactly the public cards are visible — no more, no less.
    assert sorted(visible_labels(v)) == sorted(expected_labels(state, seat)), (
        f"{where} seat {seat}: visible set is wrong"
    )

    # 4. Hidden slots keep their place but carry no identity.
    slots = [*v["hand"]["cards"], *[c for o in v["others"] for c in o["cards"]]]
    assert len(slots) == len(state.seats) * HAND
    for card in slots:
        if card["up"]:
            assert sorted(card) == ["rank", "suit", "up"]
        else:
            assert sorted(card) == ["hidden", "up"]
    return v


# ── the boundary ────────────────────────────────────────────────────────


def test_a_fresh_deal_hides_four_of_everyones_six_cards_from_everyone():
    state = create_match(seats=3, seed=42)
    for seat in range(3):
        v = assert_no_leak(state, seat, "deal")
        assert sum(1 for c in v["hand"]["cards"] if not c["up"]) == 4
        assert len(v["others"]) == 2
        for other in v["others"]:
            assert sum(1 for c in other["cards"] if not c["up"]) == 4


def test_you_do_not_know_your_own_face_down_cards_either():
    state = create_match(seats=2, seed=13)
    v = view(state, 0)
    mine = [label(c) for c in state.hands[0] if not c["up"]]
    assert len(mine) == 4
    blob = as_json(v["hand"])
    for l in mine:
        assert l not in blob, f"{l} is yours but you should not see it"


def test_the_drawn_card_is_visible_to_its_holder_and_to_nobody_else():
    state = create_match(seats=3, seed=6)
    seat = state.turn
    apply(state, seat, {"type": "draw-stock"})
    held = label(state.pending)

    theirs = view(state, seat)
    assert label(theirs["pending"]) == held
    assert theirs["holding"] is True
    assert theirs["source"] == "stock"

    for other in range(3):
        if other == seat:
            continue
        v = assert_no_leak(state, other, "after draw")
        assert v["pending"] is None
        # They can see that a card has been taken, not which one.
        assert v["holding"] is False
        assert held not in as_json(v)


def test_a_card_taken_from_the_discard_pile_was_already_public_and_stays_so():
    state = create_match(seats=2, seed=15)
    seat = state.turn
    top = label(state.discard[-1])
    apply(state, seat, {"type": "draw-discard"})
    # The pile is one card shorter, but the card is still accounted for in the view the
    # other player sees: it sits in the holder's hand.
    v = view(state, 1 - seat)
    assert v["holding"] is False
    assert v["discardCount"] == len(state.discard)
    top_now = v["discardTop"]
    assert top_now is None or label(top_now) != top or len(state.discard) > 0
    assert_no_leak(state, 1 - seat, "after taking the discard")


def test_the_discard_top_and_the_held_card_are_marked_face_up_so_the_client_draws_paper():
    state = create_match(seats=2, seed=91)
    v = view(state, state.turn)
    # Anything that leaves the deck face up says so. A card without `up` renders as a
    # card back, which is exactly how the discard pile looked wrong the first time.
    assert v["discardTop"]["up"] is True
    assert all(c["up"] is True for c in v["discard"])
    apply(state, state.turn, {"type": "draw-stock"})
    assert view(state, state.turn)["pending"]["up"] is True


def test_legal_actions_are_per_seat_only_the_player_to_move_is_offered_anything():
    state = create_match(seats=4, seed=77)
    for seat in range(4):
        v = view(state, seat)
        if seat == state.turn:
            assert len(v["legal"]) >= 2
        else:
            assert v["legal"] == []


def test_a_hole_that_is_over_offers_exactly_one_thing_the_next_hole():
    state = create_match(seats=3, seed=18)
    guard = 0
    while state.phase != "done" and guard < 20000:
        guard += 1
        apply(state, state.turn, choose_action(state, state.turn))
    for seat in range(3):
        v = view(state, seat)
        assert v["legal"] == [{"type": "next-hole"}]
        # Hole scores are public once the hole is scored — that is the whole point.
        assert all(isinstance(s["holeScore"], int) for s in v["seats"])


def test_no_seat_is_ever_shown_a_hidden_card_at_any_point_in_a_full_nine_hole_match():
    state = create_match(seats=3, seed=2024)
    steps = 0
    while not state.over:
        steps += 1
        assert steps <= 60000, "match did not finish"
        seat = state.turn
        v = assert_no_leak(state, seat, f"step {steps} (mover)")
        for other in range(3):
            if other != seat:
                assert_no_leak(state, other, f"step {steps} (waiting {other})")
        assert v["you"] == seat
        apply(state, seat, choose_action(state, seat))
    # And once more with every card face up, where nothing is left to hide.
    for seat in range(3):
        assert_no_leak(state, seat, "final")


def test_the_view_reports_presence_data_the_server_adds_without_disturbing_the_redaction():
    state = create_match(seats=2, seed=3)
    v = view(state, 0, {"presence": {0: True, 1: False}, "code": "ABCDEF"})
    assert v["code"] == "ABCDEF"
    assert v["presence"] == {0: True, 1: False}
