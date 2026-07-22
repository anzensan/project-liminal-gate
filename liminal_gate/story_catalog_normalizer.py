"""Convert an operator-authored CSV stage sheet into the strict story catalog."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from liminal_gate.story_catalog import StoryCatalogError, load_story_catalog

FIELDS = ("chapter", "section", "stamina", "coins", "clear_progress_code", "clear_coins")


def normalize(path: Path) -> dict[str, object]:
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
    except OSError as error:
        raise ValueError("could not read stage CSV") from error
    if not rows or tuple(rows[0]) != FIELDS:
        raise ValueError("CSV columns must exactly be " + ", ".join(FIELDS))
    stages = []
    for row in rows:
        try:
            stage = {name: int(row[name]) for name in FIELDS}
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("every stage value must be a decimal integer") from error
        if any(value < 0 for value in stage.values()) or stage["chapter"] < 2 or stage["section"] < 1:
            raise ValueError("stage values are outside the generic-story range")
        stages.append(stage)
    identities = [(stage["chapter"], stage["section"]) for stage in stages]
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        raise ValueError("stages must be sorted and unique by chapter, section")
    return {"schema_version": 1, "provenance": "user-supplied", "stages": stages}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-csv", type=Path, required=True)
    parser.add_argument("--output-catalog", type=Path, required=True)
    args = parser.parse_args()
    try:
        document = normalize(args.input_csv)
        args.output_catalog.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        load_story_catalog(args.output_catalog)
    except (ValueError, StoryCatalogError) as error:
        raise SystemExit(f"story catalog normalization failed: {error}") from error
    print(f"wrote {len(document['stages'])} user-supplied story stages")
    return 0
