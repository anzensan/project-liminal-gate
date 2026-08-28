from pathlib import Path
import unittest


class SaveEditorSafetyTest(unittest.TestCase):
    def test_user_supplied_values_are_not_inserted_as_unescaped_html(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "tools" / "save-editor.html"
        ).read_text(encoding="utf-8")
        self.assertNotIn('$("account").innerHTML = ids.map', source)
        self.assertIn('escapeHtml(String(row.jobID ?? 0))', source)
        self.assertIn("escapeHtml(field)", source)
        self.assertIn("escapeHtml(message)", source)

    def test_export_keeps_every_float_the_validator_requires(self) -> None:
        # The page cannot run here, so the check is on its source: every
        # float-typed field save_validation names must be one the export
        # re-emits with a decimal, or `apply` refuses the export.
        from liminal_gate.save_validation import FLOAT_FIELDS

        source = (
            Path(__file__).resolve().parents[1] / "tools" / "save-editor.html"
        ).read_text(encoding="utf-8")
        for name in FLOAT_FIELDS:
            self.assertIn(f'"{name}"', source.split("const FLOAT_KEYS")[1].split("\n")[0], name)
        self.assertIn('const FLOAT_OBJECTS = new Set(["questClearDate"]);', source)


if __name__ == "__main__":
    unittest.main()
