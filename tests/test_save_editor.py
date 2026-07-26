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


if __name__ == "__main__":
    unittest.main()
