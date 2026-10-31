"""Play a whole match with no browser and no network. The cheapest end-to-end proof.

    python -m golf --seed 42 --seats 3
    python -m golf --seed 42 --seats 3 --trace      # every action, in order

Same seed, same run, same output — which is what makes a bug report reproducible.
"""

from __future__ import annotations

import argparse
import sys

from .engine import HOLES, MAX_SEATS, MIN_SEATS, RuleError, apply, create_match, label, score_hand
from .view import view

from .policy import choose_action


def play(seats: int, seed: int, holes: int = HOLES, trace: bool = False, out=sys.stdout) -> int:
    state = create_match(seats=seats, seed=seed, holes=holes)
    history: list[dict] = []
    steps = 0
    while not state.over:
        steps += 1
        if steps > 100000:
            raise SystemExit("match did not finish — that is a bug")
        seat = state.turn
        action = choose_action(state, seat)
        if action is None:
            break
        if trace:
            print(f"  hole {state.hole} seat {seat} ({state.seats[seat]['name']}) {action}", file=out)
        apply(state, seat, action)
        if state.phase == "done":
            history.append({"hole": state.hole, "scores": list(state.hole_scores)})

    print(f"seed {seed}, {seats} seats, {len(history)} holes, {steps} actions\n", file=out)
    names = [s["name"] for s in state.seats]
    print("hole  " + "  ".join(f"{n:>8}" for n in names), file=out)
    for entry in history:
        print(f"{entry['hole']:>4}  " + "  ".join(f"{v:>8}" for v in entry["scores"]), file=out)
    print("      " + "-" * (10 * len(names)), file=out)
    totals = [s["total"] for s in state.seats]
    print("total " + "  ".join(f"{v:>8}" for v in totals), file=out)

    low = min(totals)
    winners = [names[i] for i, t in enumerate(totals) if t == low]
    print(f"\n{' & '.join(winners)} win{'s' if len(winners) == 1 else ''} at {low}", file=out)

    last = state.log[0]["text"] if state.log else ""
    print(f"last log line: {last}", file=out)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="golf", description="Play a Golf match headlessly.")
    parser.add_argument("--seats", type=int, default=3, help=f"{MIN_SEATS}-{MAX_SEATS} players")
    parser.add_argument("--seed", type=int, default=42, help="same seed, same run")
    parser.add_argument("--holes", type=int, default=HOLES)
    parser.add_argument("--trace", action="store_true", help="print every action")
    args = parser.parse_args(argv)
    try:
        return play(args.seats, args.seed, args.holes, args.trace)
    except RuleError as exc:
        print(f"golf: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
