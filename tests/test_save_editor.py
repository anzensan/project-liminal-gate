from pathlib import Path
import re
import unittest

from liminal_gate.save_validation import FLOAT_FIELDS, FLOAT_VALUE_OBJECT_FIELDS

SOURCE = (
    Path(__file__).resolve().parents[1] / "tools" / "save-editor.html"
).read_text(encoding="utf-8")


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


if __name__ == "__main__":
    unittest.main()
