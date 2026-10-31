"""The browser client is a copy, not a port — so check it has not drifted.

If the JavaScript repo is present, `public/` here must be byte-identical to
`../golf/public/`. A UI fix belongs in the source repo, followed by a re-copy; this
test is what makes "which copy is live?" a question with an answer.
"""

from __future__ import annotations

import filecmp
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
SOURCE = HERE.parent / "golf" / "public"


@pytest.mark.skipif(not SOURCE.is_dir(), reason="the JavaScript repo is not checked out beside this one")
def test_the_client_copy_matches_the_source_repo():
    mine = sorted(p.name for p in (HERE / "public").iterdir() if p.is_file())
    theirs = sorted(p.name for p in SOURCE.iterdir() if p.is_file())
    assert mine == theirs, f"file lists differ: {set(mine) ^ set(theirs)}"
    for name in theirs:
        assert filecmp.cmp(HERE / "public" / name, SOURCE / name, shallow=False), (
            f"public/{name} has drifted from ../golf/public/{name}"
        )
