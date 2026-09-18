from pathlib import Path
import re
import tempfile
import unittest

from liminal_gate import bootstrap_server
from liminal_gate.companion_catalog import build_bundled_companion_policy
from liminal_gate.companion_strengthen_catalog import build_bundled_companion_strengthen_policy
from liminal_gate.save_editor_tables import (
    BEGIN_MARKER,
    END_MARKER,
    companion_level_table,
    main,
    render_companion_table,
    replace_table,
)
from liminal_gate.save_validation import FLOAT_FIELDS, FLOAT_VALUE_OBJECT_FIELDS

EDITOR = Path(__file__).resolve().parents[1] / "tools" / "save-editor.html"
SOURCE = EDITOR.read_text(encoding="utf-8")


def _js_set(name: str) -> set[str]:
    """The literal string members of a `const <name> = new Set([...])`."""
    match = re.search(rf"const {name} = new Set\(\[(.*?)\]\);", SOURCE, re.S)
    if match is None:
        raise AssertionError(f"{name} is no longer declared as a Set literal")
    return set(re.findall(r'"([^"]+)"', match.group(1)))


class SaveEditorSafetyTest(unittest.TestCase):
    def test_user_supplied_values_are_not_inserted_as_unescaped_html(self) -> None:
        self.assertNotIn('$("account").innerHTML = ids.map', SOURCE)
        self.assertIn('escapeHtml(String(row.jobID ?? 0))', SOURCE)
        self.assertIn("escapeHtml(field)", SOURCE)
        self.assertIn("escapeHtml(message)", SOURCE)
        # Companion names come from the same user-supplied file as character
        # names and reach innerHTML through the same two paths.
        self.assertIn('escapeHtml(nameFor("companions", companion.bid))', SOURCE)
        self.assertIn("escapeHtml(equipped)", SOURCE)
        self.assertIn('Object.entries(names.companions)', SOURCE)
        self.assertIn('escapeHtml(`${name} (${id})`)', SOURCE)


class SaveEditorFloatFieldsTest(unittest.TestCase):
    """The editor re-emits decimals that `JSON.stringify` would flatten, and
    `save_validation` refuses a save that lost one. The two hold the same list
    in two languages, and nothing but this test compares them: `questClearDate`
    was missing from the editor's, so exporting a real account produced one
    error per cleared stage and a save that would not apply. See issue 75."""

    def test_the_editor_marks_every_field_the_validator_requires_as_decimal(self) -> None:
        self.assertEqual(set(FLOAT_FIELDS), _js_set("FLOAT_KEYS"))

    def test_the_editor_marks_every_object_whose_values_are_decimals(self) -> None:
        self.assertEqual(set(FLOAT_VALUE_OBJECT_FIELDS), _js_set("FLOAT_VALUE_OBJECTS"))


class CompanionLevelFieldTest(unittest.TestCase):
    """Typing a level must not rebuild the row under the caret.

    `renderCompanions` replaces the whole table body, so a re-render from the
    `input` handler removes the field being typed into and the focus falls to
    the document: the second digit of a two-digit level goes nowhere, and the
    level can only ever be set one digit at a time. The roster's level field
    has always called `check()` alone for exactly this reason. The Companion
    table refreshes its one derived cell in place instead, and defers the
    re-render to `change`, which fires once the field is committed and is where
    a value above the cap is shown as the value it was clamped to.
    """

    def _handler(self, event: str) -> str:
        marker = f'$("companions").addEventListener("{event}"'
        self.assertIn(marker, SOURCE, event)
        return SOURCE.split(marker)[1].split("});")[0]

    def test_typing_a_level_does_not_rebuild_the_table(self) -> None:
        handler = self._handler("input")
        self.assertNotIn("render()", handler)
        self.assertIn("check()", handler)
        # The EXP the level derives is the one thing the row displays that the
        # model changes, so it is refreshed in place rather than by a rebuild.
        self.assertIn("data-companion-exp", handler)
        self.assertIn('data-companion-exp="${index}"', SOURCE)

    def test_committing_the_field_re_renders(self) -> None:
        self.assertIn("render()", self._handler("change"))


class CompanionProgressionTableTest(unittest.TestCase):
    """The page's copy of the progression curve must be the server's curve.

    Three links are checked: the block in the page equals what the module
    renders; the module's thresholds equal `bootstrap_server._companion_exp_at`
    for every master and level -- both read
    `companion_progression_data.companion_exp_at`, so this pins the data path
    (progression rows here, catalog masters there) rather than the formula;
    and every threshold decodes back to its own level through
    `_companion_level_at_exp`, which is what the server does on the next
    strengthen. A failure of the first is fixed by re-running
    `python3 -m liminal_gate.save_editor_tables tools/save-editor.html`.
    """

    def test_page_carries_the_rendered_table(self) -> None:
        self.assertIn(render_companion_table(), SOURCE)
        self.assertEqual(SOURCE.count(BEGIN_MARKER), 1)
        self.assertEqual(SOURCE.count(END_MARKER), 1)

    def test_thresholds_match_the_server_and_round_trip(self) -> None:
        catalog = build_bundled_companion_strengthen_policy()
        by_id = {companion_id: profile for profile in companion_level_table() for companion_id in profile["ids"]}
        self.assertEqual(set(by_id), set(catalog.masters))
        for companion_id, master in catalog.masters.items():
            profile = by_id[companion_id]
            self.assertEqual(profile["max"], master.max_level)
            self.assertEqual(len(profile["exp"]), master.max_level - 1)
            for level in range(1, master.max_level + 1):
                exp = 0 if level == 1 else profile["exp"][level - 2]
                self.assertEqual(exp, bootstrap_server._companion_exp_at(master, level), (companion_id, level))
                self.assertEqual(bootstrap_server._companion_level_at_exp(master, exp), level, (companion_id, level))

    def test_every_master_the_server_sells_has_a_profile(self) -> None:
        # The editor refuses a master outside its table, so the table must
        # cover every master the sale catalog knows, or a real Companion
        # could not be added.
        ids = [companion_id for profile in companion_level_table() for companion_id in profile["ids"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), set(build_bundled_companion_policy().masters))

    def test_replace_table_requires_both_markers_in_order(self) -> None:
        with self.assertRaises(ValueError) as caught:
            replace_table(f"{END_MARKER}\n{BEGIN_MARKER}\n")
        self.assertEqual(
            str(caught.exception),
            "the page does not carry both Companion progression table markers, in order",
        )
        with self.assertRaises(ValueError):
            replace_table("no markers at all")

    def test_main_rewrites_a_stale_page_and_leaves_a_current_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            page = Path(directory) / "page.html"
            page.write_text(f"before\n{BEGIN_MARKER}\nstale\n{END_MARKER}\nafter\n", encoding="utf-8")
            self.assertEqual(main([str(page)]), 0)
            self.assertEqual(page.read_text(encoding="utf-8"), f"before\n{render_companion_table()}\nafter\n")
            unchanged = page.read_text(encoding="utf-8")
            self.assertEqual(main([str(page)]), 0)
            self.assertEqual(page.read_text(encoding="utf-8"), unchanged)
            self.assertEqual(main(["one", "two"]), 2)


if __name__ == "__main__":
    unittest.main()
