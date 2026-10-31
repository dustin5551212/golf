"""Golf — six-card, nine holes. Python implementation of the rules and server.

The engine (``golf.engine``) is the whole game in one object; ``golf.view`` is the
only place that decides what leaves the server; ``golf.server`` is the HTTP/SSE
transport. The browser client in ``public/`` is unchanged from the JavaScript
version — this port replaces the server, not the UI.
"""

from .engine import (
    COLS,
    HAND,
    HOLES,
    MAX_SEATS,
    MIN_SEATS,
    RANKS,
    SUITS,
    RuleError,
    State,
    apply,
    build_deck,
    card_value,
    create_match,
    is_red,
    label,
    legal_actions,
    make_rng,
    score_hand,
    shuffle,
)
from .view import view, view_for

__all__ = [
    "COLS", "HAND", "HOLES", "MAX_SEATS", "MIN_SEATS", "RANKS", "SUITS",
    "RuleError", "State", "apply", "build_deck", "card_value", "create_match",
    "is_red", "label", "legal_actions", "make_rng", "score_hand", "shuffle",
    "view", "view_for",
]
__version__ = "0.1.0"
