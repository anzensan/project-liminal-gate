"""The Companion progression table `tools/save-editor.html` carries.

The save editor is one file with no network access, so it cannot read
:mod:`liminal_gate.companion_progression_data` at runtime; it carries a copy of
what it needs, rendered by this module.  What it needs is, per Companion, the
level cap and the EXP the server expects at each level: `bootstrap_server`
recomputes `lv` from `exp` whenever a Companion is strengthened
(`_companion_level_at_exp`), so a Companion written with a level and an EXP
that disagree keeps the level only until its first strengthen.  The editor
writes both from this table and cannot get them out of step.

The thresholds are precomputed here rather than by the formula in the page
because JavaScript's `Math.pow` and Python's `**` are not guaranteed to agree
in the last bit, and `floor` turns a last-bit disagreement into an EXP one
below the level's threshold -- which the server then reads as the level below.
`tests/test_save_editor.py` checks the block in the page against this module,
and this module against `bootstrap_server._companion_exp_at`, so the three
cannot drift apart without a test saying so.

Regenerate the page's copy after changing the progression data:

    python3 -m liminal_gate.save_editor_tables tools/save-editor.html
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
from typing import Any

from liminal_gate.companion_progression_data import COMPANION_PROGRESSION_ROWS

BEGIN_MARKER = "// BEGIN generated Companion progression table"
END_MARKER = "// END generated Companion progression table"


def companion_exp_at(exp_max: int, exp_coeff: float, level: int) -> int:
    """The EXP a Companion holds on reaching `level`.

    The same expression as `bootstrap_server._companion_exp_at`, kept in step
    by test rather than by import: importing the server here would pull ~30
    catalogs into a table renderer.
    """
    if level <= 1:
        return 0
    return math.floor(exp_max * ((level - 1) / 98.0) ** exp_coeff)


def companion_level_table() -> list[dict[str, Any]]:
    """Group the masters by progression profile and list each level's EXP.

    A profile is one (level cap, EXP ceiling, curve exponent) triple; 497
    masters fall into two dozen of them, so the page carries each threshold
    list once with the ids that share it.  `exp[k]` is the EXP at level
    `k + 2`; level 1 is always 0 and is not stored.
    """
    profiles: dict[tuple[int, int, float], list[int]] = {}
    for companion_id, _base_exp, max_level, exp_max, exp_coeff, _bias in COMPANION_PROGRESSION_ROWS:
        profiles.setdefault((max_level, exp_max, exp_coeff), []).append(companion_id)
    table = []
    for (max_level, exp_max, exp_coeff), ids in sorted(profiles.items()):
        table.append({
            "max": max_level,
            "exp": [companion_exp_at(exp_max, exp_coeff, level) for level in range(2, max_level + 1)],
            "ids": sorted(ids),
        })
    return table


def render_companion_table() -> str:
    """The exact text between the page's markers, one profile per line."""
    lines = [
        BEGIN_MARKER,
        "// Rendered from liminal_gate/companion_progression_data.py by",
        "// `python3 -m liminal_gate.save_editor_tables tools/save-editor.html`.",
        "// Do not edit by hand: tests/test_save_editor.py compares it to the source.",
        "const COMPANION_PROGRESSION = [",
    ]
    for profile in companion_level_table():
        lines.append(
            "  {max: %d, exp: %s, ids: %s},"
            % (profile["max"], json.dumps(profile["exp"], separators=(",", ":")), json.dumps(profile["ids"], separators=(",", ":")))
        )
    lines.append("];")
    lines.append(END_MARKER)
    return "\n".join(lines)


def replace_table(source: str) -> str:
    """Return `source` with the block between the markers re-rendered."""
    start = source.find(BEGIN_MARKER)
    end = source.find(END_MARKER)
    if start < 0 or end < 0 or end < start:
        raise ValueError("the page does not carry both Companion progression table markers, in order")
    return source[:start] + render_companion_table() + source[end + len(END_MARKER):]


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments:
        print(render_companion_table())
        return 0
    if len(arguments) != 1:
        print("usage: python3 -m liminal_gate.save_editor_tables [tools/save-editor.html]", file=sys.stderr)
        return 2
    page = Path(arguments[0])
    original = page.read_text(encoding="utf-8")
    updated = replace_table(original)
    if updated == original:
        print(f"{page}: Companion progression table already current")
        return 0
    page.write_text(updated, encoding="utf-8")
    print(f"{page}: Companion progression table rewritten")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
