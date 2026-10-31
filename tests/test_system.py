"""The whole system, joined: deal → decide → resolve → score → terminate.

Unit tests prove the rules; the parity suite proves rule-by-rule equivalence with the
JavaScript source. This file asserts the properties that only appear when a match is
played through: conservation, totals that reconcile, and determinism.
"""

from __future__ import annotations

import json
import subprocess
import sys

from golf.engine import HOLES, apply, card_value, create_match, score_hand
from golf.policy import choose_action
from golf.snapshot import snapshot


def all_cards(state) -> list[dict]:
    cards = [*state.stock, *state.discard]
    for hand in state.hands:
        cards.extend(hand)
    if state.pending:
        cards.append(state.pending)
    return cards


def labels(cards: list[dict]) -> list[str]:
    return [c["rank"] + c["suit"] for c in cards]


def play_out(seats: int, seed: int) -> tuple[object, list[dict]]:
    """Play a full match, asserting conservation at every single step."""
    state = create_match(seats=seats, seed=seed)
    history: list[dict] = []
    steps = 0
    while not state.over:
        steps += 1
        assert steps <= 100000, "match did not finish"

        cards = all_cards(state)
        assert len(cards) == 52, f"step {steps}: {len(cards)} cards on the table"
        assert len(set(labels(cards))) == 52, f"step {steps}: a card is duplicated or invented"

        apply(state, state.turn, choose_action(state, state.turn))
        if state.phase == "done":
            history.append({"hole": state.hole, "scores": list(state.hole_scores)})
    return state, history


def test_a_full_match_conserves_all_52_cards_at_every_step():
    for seats, seed in ((2, 31), (3, 99), (4, 777)):
        state, history = play_out(seats, seed)
        assert state.hole == HOLES
        assert state.over is True
        assert state.phase == "done"
        assert len(history) == HOLES, f"{seats}/{seed}: scored {len(history)} holes, not 9"


def test_every_seats_total_is_exactly_the_sum_of_the_holes_it_scored():
    for seats, seed in ((2, 31), (3, 808), (4, 17)):
        state, history = play_out(seats, seed)
        for seat in range(seats):
            expected = sum(h["scores"][seat] for h in history)
            assert state.seats[seat]["total"] == expected, f"{seats}/{seed} seat {seat}"


def test_each_published_hole_score_equals_an_independent_scoring_of_that_grid():
    state, history = play_out(3, 4242)
    assert len(history) == HOLES
    # The grids are all face up at the end of a hole, so a separate scorer can redo them.
    for hand, reported in zip(state.hands, state.hole_scores):
        assert score_hand(hand)["total"] == reported


def test_the_same_seed_produces_a_byte_identical_run():
    def run(seed: int) -> str:
        state = create_match(seats=3, seed=seed)
        trace = []
        while not state.over:
            apply(state, state.turn, choose_action(state, state.turn))
            trace.append(snapshot(state))
        return json.dumps(trace, sort_keys=True, ensure_ascii=False)

    first, second = run(31), run(31)
    assert first == second, "same seed, different run — the engine is not deterministic"
    assert run(32) != first, "a different seed changed nothing — the seed is being ignored"


def test_the_headless_cli_prints_a_whole_match():
    result = subprocess.run(
        [sys.executable, "-m", "golf", "--seed", "42", "--seats", "3"],
        capture_output=True,
        text=True,
        cwd=str(__import__("pathlib").Path(__file__).resolve().parent.parent),
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "9 holes" in out
    assert "total" in out
    assert "win" in out
    # One row per hole plus the total row.
    rows = [line for line in out.splitlines() if line[:4].strip().isdigit()]
    assert len(rows) == HOLES, f"expected 9 hole rows, got {len(rows)}: {out}"
