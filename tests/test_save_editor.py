from pathlib import Path
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

EDITOR = Path(__file__).resolve().parents[1] / "tools" / "save-editor.html"


class SaveEditorSafetyTest(unittest.TestCase):
    def test_user_supplied_values_are_not_inserted_as_unescaped_html(self) -> None:
        source = EDITOR.read_text(encoding="utf-8")
        self.assertNotIn('$("account").innerHTML = ids.map', source)
        self.assertIn('escapeHtml(String(row.jobID ?? 0))', source)
        self.assertIn("escapeHtml(field)", source)
        self.assertIn("escapeHtml(message)", source)
        # Companion names come from the same user-supplied file as character
        # names and reach innerHTML through the same two paths.
        self.assertIn('escapeHtml(nameFor("companions", companion.bid))', source)
        self.assertIn("escapeHtml(equipped)", source)
        self.assertIn('Object.entries(names.companions)', source)
        self.assertIn('escapeHtml(`${name} (${id})`)', source)

    def test_export_keeps_every_float_the_validator_requires(self) -> None:
        # The page cannot run here, so the check is on its source: every
        # float-typed field save_validation names must be one the export
        # re-emits with a decimal, or `apply` refuses the export.
        from liminal_gate.save_validation import FLOAT_FIELDS

        source = EDITOR.read_text(encoding="utf-8")
        for name in FLOAT_FIELDS:
            self.assertIn(f'"{name}"', source.split("const FLOAT_KEYS")[1].split("\n")[0], name)
        self.assertIn('const FLOAT_OBJECTS = new Set(["questClearDate"]);', source)


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
        source = EDITOR.read_text(encoding="utf-8")
        self.assertIn(render_companion_table(), source)
        self.assertEqual(source.count(BEGIN_MARKER), 1)
        self.assertEqual(source.count(END_MARKER), 1)

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
