import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.event_character_catalog import EventCharacterCatalogError, load_event_character_catalog


class EventCharacterCatalogTest(unittest.TestCase):
    def _character_document(self) -> dict[str, object]:
        return {"schema_version": 1, "provenance": "user-derived", "characters": [{"character_id": 3}, {"character_id": 25}]}

    def _load(self, event_document: dict[str, object]) -> object:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); characters = root / "characters.json"; events = root / "events.json"
            characters.write_text(json.dumps(self._character_document()), encoding="utf-8")
            event_document["character_catalog_sha256"] = hashlib.sha256(characters.read_bytes()).hexdigest()
            events.write_text(json.dumps(event_document), encoding="utf-8")
            return load_event_character_catalog(events, characters)

    def test_loads_only_members_present_in_local_catalog(self) -> None:
        catalog = self._load({"schema_version": 1, "provenance": "user-supplied", "character_catalog_sha256": "", "events": [{"event_id": "local-event", "character_ids": [3, 25]}]})
        self.assertEqual({"local-event": frozenset({3, 25})}, catalog.event_characters)

    def test_rejects_missing_local_character(self) -> None:
        with self.assertRaisesRegex(EventCharacterCatalogError, "absent"):
            self._load({"schema_version": 1, "provenance": "user-supplied", "character_catalog_sha256": "", "events": [{"event_id": "local-event", "character_ids": [99]}]})

    def test_rejects_changed_character_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); characters = root / "characters.json"; events = root / "events.json"
            characters.write_text(json.dumps(self._character_document()), encoding="utf-8")
            events.write_text(json.dumps({"schema_version": 1, "provenance": "user-supplied", "character_catalog_sha256": "0" * 64, "events": [{"event_id": "local-event", "character_ids": [3]}]}), encoding="utf-8")
            with self.assertRaisesRegex(EventCharacterCatalogError, "does not match"):
                load_event_character_catalog(events, characters)
