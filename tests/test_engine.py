"""The rules suite, re-expressed in Python idiom from ``golf/src/engine.test.js``.

This is the readable specification; ``test_parity.py`` is the evidence that it matches
the shipped implementation. Where the source test hard-codes an outcome (a hole score,
a turn count) the number is re-derived from the source's own behaviour, not computed
by hand.
"""

from __future__ import annotations

import pytest

from golf.engine import (
    COLS,
    HAND,
    HOLES,
    KNOCK_MIN_UP,
    RuleError,
    apply,
    build_deck,
    card_value,
    create_match,
    knock_ready,
    legal_actions,
    score_hand,
)
from golf.policy import choose_action

# ── an independent scoring implementation, written a second way ─────────

REFERENCE_KEYS = {"A": 1, "2": -2, "J": 10, "Q": 10, "K": 0}


def reference_score(hand: list[dict]) -> int:
    val = lambda rank: REFERENCE_KEYS[rank] if rank in REFERENCE_KEYS else int(rank)  # noqa: E731
    total = 0
    for i, j in ((0, 3), (1, 4), (2, 5)):
        if hand[i]["rank"] == hand[j]["rank"]:
            continue
        total += val(hand[i]["rank"]) + val(hand[j]["rank"])
    return total


def all_cards(state) -> list[dict]:
    cards = [*state.stock, *state.discard]
    for hand in state.hands:
        cards.extend(hand)
    if state.pending:
        cards.append(state.pending)
    return cards


# ── deck and scoring ────────────────────────────────────────────────────


def test_a_deck_is_52_unique_cards():
    deck = build_deck()
    assert len(deck) == 52
    assert len({c["rank"] + c["suit"] for c in deck}) == 52


def test_card_values_are_the_ones_printed_on_the_table():
    assert card_value("A") == 1
    assert card_value("2") == -2
    assert card_value("K") == 0
    assert card_value("J") == 10
    assert card_value("Q") == 10
    assert card_value("7") == 7
    assert card_value("10") == 10


def test_a_column_of_equal_ranks_scores_zero_whatever_they_are():
    hand = [{"rank": r, "suit": "\u2660"} for r in ["9", "A", "K", "9", "A", "2"]]
    result = score_hand(hand)
    assert [c["pair"] for c in result["cols"]] == [True, True, False]
    assert result["total"] == 0 + 0 + (0 + -2)  # two pairs (9s and As) plus K+2


def test_the_grid_is_three_columns_each_pairing_a_card_with_the_one_three_seats_away():
    assert [list(c) for c in COLS] == [[0, 3], [1, 4], [2, 5]]
    assert HAND == 6
    assert HOLES == 9


# ── dealing ─────────────────────────────────────────────────────────────


def test_every_player_gets_six_cards_two_face_up_and_the_rest_is_stock():
    state = create_match(seats=["Ada", "Bert", "Cass"], seed=7)
    for hand in state.hands:
        assert len(hand) == 6
        assert [c["up"] for c in hand] == [True, False, False, True, False, False]
    assert len(state.discard) == 1
    assert len(state.stock) == 52 - 3 * 6 - 1
    assert len(all_cards(state)) == 52


def test_the_same_seed_deals_the_same_cards():
    a = create_match(seats=3, seed=12345)
    b = create_match(seats=3, seed=12345)
    assert a.hands == b.hands
    assert a.stock == b.stock


def test_a_table_is_2_to_4_people_golf_is_not_a_solitaire():
    with pytest.raises(RuleError):
        create_match(seats=1)
    with pytest.raises(RuleError):
        create_match(seats=5)
    for n in (2, 3, 4):
        assert len(create_match(seats=n, seed=1).hands) == n


# ── turn rules ──────────────────────────────────────────────────────────


def test_only_the_player_whose_turn_it_is_may_act():
    state = create_match(seats=3, seed=3)
    not_turn = (state.turn + 1) % 3
    with pytest.raises(RuleError, match="not your turn"):
        apply(state, not_turn, {"type": "draw-stock"})


def test_a_card_taken_from_the_discard_pile_cannot_be_thrown_straight_back():
    state = create_match(seats=2, seed=11)
    apply(state, state.turn, {"type": "draw-discard"})
    assert state.phase == "swap"
    assert state.source == "discard"
    with pytest.raises(RuleError, match="must be placed"):
        apply(state, state.turn, {"type": "discard"})
    apply(state, state.turn, {"type": "swap", "slot": 2})
    assert state.phase == "draw"


def test_throwing_away_the_drawn_card_is_a_pass_and_no_card_is_turned_up():
    state = create_match(seats=2, seed=5)
    seat = state.turn
    up_before = sum(1 for c in state.hands[seat] if c["up"])
    discards_before = len(state.discard)

    apply(state, seat, {"type": "draw-stock"})
    # House rule: there is no flip phase to pay for the pass.
    with pytest.raises(RuleError, match="unknown action"):
        apply(state, seat, {"type": "flip", "slot": 1})

    apply(state, seat, {"type": "discard"})
    assert len(state.discard) == discards_before + 1, "the card goes on the pile"
    assert sum(1 for c in state.hands[seat] if c["up"]) == up_before, "nothing is revealed"
    assert state.phase == "draw"
    assert state.turn == (seat + 1) % 2, "the turn passes"
    assert state.pending is None


def test_legal_actions_describe_exactly_what_the_player_may_do():
    state = create_match(seats=3, seed=21)
    seat = state.turn
    assert legal_actions(state, seat) == [{"type": "draw-stock"}, {"type": "draw-discard"}]
    assert legal_actions(state, (seat + 1) % 3) == []

    apply(state, seat, {"type": "draw-stock"})
    swaps = legal_actions(state, seat)
    assert sum(1 for a in swaps if a["type"] == "swap") == 6
    assert sum(1 for a in swaps if a["type"] == "discard") == 1

    apply(state, seat, {"type": "swap", "slot": 4})
    assert legal_actions(state, (seat + 1) % 3) == [{"type": "draw-stock"}, {"type": "draw-discard"}]


# ── the whole game ──────────────────────────────────────────────────────


def play_until(seat_count: int, predicate, seed: int, limit: int = 60000):
    state = create_match(seats=seat_count, seed=seed)
    steps = 0
    while not predicate(state):
        steps += 1
        if steps > limit:
            raise AssertionError("game did not finish")
        action = choose_action(state, state.turn)
        if action is None:
            break
        apply(state, state.turn, action)
    return state


def test_nine_holes_played_to_the_end_keep_52_cards_on_the_table_at_every_step():
    state = create_match(seats=3, seed=99)
    steps = 0
    while not state.over:
        steps += 1
        assert steps <= 50000, "match did not finish"
        assert len(all_cards(state)) == 52, f"card count broke at step {steps}"
        apply(state, state.turn, choose_action(state, state.turn))
    assert state.hole == 9
    assert state.phase == "done"
    assert len(state.hole_scores) == 3
    assert all(isinstance(s["total"], int) for s in state.seats)


def test_hole_scores_agree_with_an_independently_written_scorer_and_totals_add_up():
    for seed in (1, 2, 3, 17, 404):
        state = create_match(seats=4, seed=seed)
        steps = 0
        while not state.over and steps < 80000:
            steps += 1
            if state.phase == "done":
                for i, hand in enumerate(state.hands):
                    assert state.hole_scores[i] == reference_score(hand), f"seed {seed} hole {state.hole}"
            apply(state, state.turn, choose_action(state, state.turn))

        # Every seat's total is the sum of the holes it scored — replayed from a log of
        # hole scores the engine itself never stores, so this is not circular.
        replay = create_match(seats=4, seed=seed)
        sums = [0, 0, 0, 0]
        guard = 0
        while not replay.over and guard < 80000:
            guard += 1
            apply(replay, replay.turn, choose_action(replay, replay.turn))
            if replay.phase == "done":
                for i, hs in enumerate(replay.hole_scores):
                    sums[i] += hs
        assert [s["total"] for s in replay.seats] == sums


def test_when_one_player_is_out_everyone_else_gets_exactly_one_more_turn():
    state = create_match(seats=3, seed=8)
    guard = 0
    out_seat = None
    while not state.ending and guard < 20000:
        guard += 1
        out_seat = state.turn
        apply(state, state.turn, choose_action(state, state.turn))
    assert state.ending, "never reached the endgame"

    # A turn is a draw, not an action: drawing, then swapping (or throwing away) is one
    # turn. Count the seats that start a draw from here on.
    turns = []
    steps = 0
    while state.phase != "done" and steps < 20:
        steps += 1
        if state.phase == "draw":
            turns.append(state.turn)
        apply(state, state.turn, choose_action(state, state.turn))
    assert state.phase == "done"
    assert len(turns) == 2, f"expected two turns after the grid filled, saw {len(turns)}"
    assert out_seat not in turns, "the player who went out should not play again"
    assert sorted(set(turns)) == [s for s in (0, 1, 2) if s != out_seat]


# ── between holes ───────────────────────────────────────────────────────


def test_a_new_hole_is_dealt_from_a_fresh_deck_and_anyone_may_move_it_on():
    state = play_until(3, lambda s: s.phase == "done", 55)
    hole = state.hole
    scores = list(state.hole_scores)
    apply(state, 2, {"type": "next-hole"})
    assert state.hole == hole + 1
    assert state.phase == "draw"
    assert state.hole_scores == [None, None, None]
    assert len(all_cards(state)) == 52
    assert state.hole_scores != scores


def test_the_game_refuses_to_jump_a_hole_that_is_still_being_played():
    state = create_match(seats=2, seed=2)
    with pytest.raises(RuleError, match="still being played"):
        apply(state, 0, {"type": "next-hole"})


def test_after_the_ninth_hole_there_is_no_tenth():
    state = play_until(2, lambda s: s.over, 31, limit=60000)
    assert state.phase == "done"
    with pytest.raises(RuleError, match="match is over"):
        apply(state, 0, {"type": "next-hole"})


def test_nonsense_actions_are_refused_rather_than_silently_ignored():
    state = create_match(seats=2, seed=4)
    seat = state.turn
    with pytest.raises(RuleError, match="no action"):
        apply(state, seat, None)
    with pytest.raises(RuleError, match="unknown action"):
        apply(state, seat, {"type": "deal-me-an-ace"})
    with pytest.raises(RuleError, match="no such seat"):
        apply(state, 9, {"type": "draw-stock"})
    with pytest.raises(RuleError, match="nothing to place"):
        apply(state, state.turn, {"type": "swap", "slot": 6})
    # A missing slot renders as `undefined` in JavaScript and `None` here; both refuse.
    apply(state, state.turn, {"type": "draw-stock"})
    with pytest.raises(RuleError, match="no such slot"):
        apply(state, state.turn, {"type": "swap"})

# ── knocking ────────────────────────────────────────────────────────────


def play_to_knock_ready(seats: int, seed: int):
    """Play with the deterministic bot until every grid shows three cards."""
    state = create_match(seats=seats, seed=seed)
    guard = 0
    while not knock_ready(state) and guard < 20000:
        guard += 1
        if state.phase == "done":
            break
        apply(state, state.turn, choose_action(state, state.turn))
    return state


def test_nobody_may_knock_until_every_grid_shows_three_cards():
    state = create_match(seats=3, seed=10)
    seat = state.turn

    assert KNOCK_MIN_UP == 3
    assert knock_ready(state) is False, "a fresh deal has two cards up each"
    assert not any(a["type"] == "knock" for a in legal_actions(state, seat)), "and it is not offered"

    with pytest.raises(RuleError, match="every grid needs 3 cards showing"):
        apply(state, seat, {"type": "knock"})


def test_once_every_grid_shows_three_cards_anyone_may_knock_and_the_hole_ends():
    state = play_to_knock_ready(3, 10)
    assert knock_ready(state), "never reached three cards showing in every grid"
    assert state.phase == "draw", "knocking is offered between turns, not mid-swap"

    knocker = (state.turn + 1) % 3  # deliberately not the player to move
    assert any(a["type"] == "knock" for a in legal_actions(state, knocker)), "every seat is offered it"

    before = [s["total"] for s in state.seats]
    apply(state, knocker, {"type": "knock"})

    assert state.phase == "done"
    assert state.pending is None
    assert all(c["up"] for hand in state.hands for c in hand), "every card turns face up"
    assert all(isinstance(s, int) for s in state.hole_scores), "the hole is scored"
    assert state.seats[knocker]["total"] == before[knocker] + state.hole_scores[knocker]
    knock_line = next(e for e in state.log if e["text"].endswith("knocked"))
    assert knock_line["text"] == f"{state.seats[knocker]['name']} knocked"
    assert knock_line["hl"] is True


def test_a_knock_waits_for_the_turn_already_in_progress():
    state = play_to_knock_ready(2, 14)
    assert knock_ready(state)

    apply(state, state.turn, {"type": "draw-stock"})
    assert state.phase == "swap"
    other = (state.turn + 1) % 2
    with pytest.raises(RuleError, match="finish the turn in progress"):
        apply(state, other, {"type": "knock"})
    assert not any(a["type"] == "knock" for a in legal_actions(state, other)), "not offered mid-swap"


def test_the_hole_after_a_knock_is_over_next_hole_and_no_second_knock():
    state = play_to_knock_ready(3, 10)
    knocker = (state.turn + 1) % 3
    apply(state, knocker, {"type": "knock"})

    with pytest.raises(RuleError, match="the hole is over"):
        apply(state, knocker, {"type": "knock"})
    assert legal_actions(state, knocker) == [{"type": "next-hole"}]

    hole = state.hole
    apply(state, knocker, {"type": "next-hole"})
    assert state.hole == hole + 1
    assert state.phase == "draw"
    assert knock_ready(state) is False, "a fresh hole is not knockable"
