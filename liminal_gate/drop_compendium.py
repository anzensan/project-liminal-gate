"""Render the local drop compendium: what drops, where, and on what evidence.

This is a *reference document*, not a server input.  Nothing loads it, no
deployment consumes it, and the server's behaviour does not change when it is
absent -- which is exactly why it can be generated freely from the same recovered
data the outcome catalog already rests on.

Why it exists
-------------

The story-outcome catalog answers "may this stage yield this?" because that is
all a settlement check needs.  It therefore discards three things a player wants:
the drop *rates* the recovered tables state, the *identity* of the enemy carrying
each drop, and the direction of the index -- the catalog is keyed by stage, while
the question people actually ask is "where do I get this?".  All three are in the
same records, so this re-reads them and inverts the join.

Agreement with the catalog is not assumed
-----------------------------------------

The per-stage ceilings rendered here are recomputed, not copied.  When the
generated catalog is available the two are compared stage by stage and any
disagreement is reported, so a page claiming to describe a server cannot quietly
drift from the one it describes.  The section-skew gate is imported from
:mod:`liminal_gate.story_outcome_generator` rather than restated, for the same
reason: a second copy of that rule would be a second thing to keep true.

What it will not say
--------------------

A stage whose encounters did not resolve is rendered as *unknown*, never as
*nothing*, and a Companion known only from a section allowlist is shown with its
per-clear cap and no rate, because the allowlist states no rate.  The page says
which of those two it is on every row rather than flattening them into one table
of apparent facts.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from html import escape
import json
from pathlib import Path
from typing import Any
import zipfile

from liminal_gate.atomic_json import write_json_document  # noqa: F401  (parity of imports checked by tests)
from liminal_gate.character_catalog_importer import load_master_trees
from liminal_gate.file_digests import sha256_file
from liminal_gate.master_strings import (
    DEFAULT_LANGUAGE, MasterStringError, decrypt_encrypted_string, load_inverse_table,
)
from liminal_gate.reviewed_build import IL2CPP_METADATA_MEMBER
from liminal_gate.story_outcome_generator import chapters_whose_sections_align

SCHEMA_VERSION = 1

#: The name guided setup writes it under, beside the catalogs it describes.
DEFAULT_DROP_COMPENDIUM = "drop-compendium.html"


class DropCompendiumError(ValueError):
    """The compendium cannot be built from the supplied local inputs."""


#: Chapter families, each read from a record in this repository rather than
#: inferred from the number.  A range with no such record keeps a neutral label:
#: a wrong name on a stage list is worse than no name, because it is the one
#: thing a reader has no way to check.
NAMED_CHAPTERS = {
    1100: "World Map Special", 1200: "Dragon Road", 1201: "Machine Road",
    3000: "Metal Zone", 3001: "Gormandizer Hunt", 3002: "Attack of the Coin Creeps",
    3003: "Money Money Time", 3004: "Crystal Road", 3100: "The Hunt For Joker",
    3200: "Blade Falcon", 3201: "Bone Killer", 3202: "Ethereal", 3300: "KINO World",
    1001: "Pudding Time", 1002: "Tin Parade", 1004: "Puppet Show",
    7000: "Orbling Cavern", 7010: "Cryptid Forest",
}


def family_of(chapter: int) -> str:
    """Label a chapter with the family this project has evidence for."""
    if chapter == 1:
        return "Tutorial"
    if 2 <= chapter <= 42:
        return "Core story"
    # `InitData` seeds world 1 at chapter 100 and world 2 at chapter 110.
    if 100 <= chapter <= 104:
        return "BreaSoul (side world)"
    if 110 <= chapter <= 119:
        return "Five Emperors (side world)"
    if chapter in NAMED_CHAPTERS:
        return NAMED_CHAPTERS[chapter]
    if 1000 <= chapter <= 1099:
        return "Hunting Zone"
    if 1300 <= chapter <= 1399:
        return "Time attack"
    if 2000 <= chapter <= 2999:
        return "Archived event"
    # Identified by their own spawns: each of the twelve at 4000--4011 places the
    # boss its 4100-block counterpart is named for.
    if 4000 <= chapter <= 4011:
        return "Eidolon quest (4000 block)"
    if 4100 <= chapter <= 4111:
        return "Eidolon quest"
    if 6000 <= chapter <= 6012:
        return "Daily quest"
    if 8000 <= chapter <= 8999:
        return "Counter Descent"
    if 9000 <= chapter <= 9009:
        return "Tower of Temptation"
    if 9010 <= chapter <= 9099:
        return "Tower of Temptation (unbannered copy)"
    if 9100 <= chapter <= 9199:
        return "Melting Pot"
    return f"Unclassified (chapter {chapter})"


def decode_enemy_names(
    enemy_data: dict[str, Any], inverse_table: bytes, language: str = DEFAULT_LANGUAGE,
) -> dict[int, str]:
    """Decode each enemy record's own localized name, locally.

    A failure to decode one name leaves that enemy showing its record ID, which
    is a worse page but not a wrong one, so it is not fatal.
    """
    rows = enemy_data.get("data")
    if not isinstance(rows, list) or not rows:
        raise DropCompendiumError("EnemyData must contain a nonempty data array")
    names: dict[int, str] = {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get("ID")) is not int:
            raise DropCompendiumError("EnemyData record has an invalid ID")
        localized = row.get("NameString")
        if not isinstance(localized, dict):
            continue
        try:
            decoded = decrypt_encrypted_string(localized.get(language), inverse_table)
        except (MasterStringError, ValueError, TypeError):
            continue
        if decoded:
            names[row["ID"]] = decoded
    return names


def enemy_drop_profiles(
    enemy_data: dict[str, Any], chr_database: dict[str, Any], enemy_names: dict[int, str],
) -> dict[int, dict[str, Any]]:
    """Read every drop channel an enemy record carries, rates included.

    Four channels, and they are not interchangeable.  ``DropBuddyID`` names a
    Companion and ``DropBuddyRatio`` its rate; ``DropJobID`` names a
    ``ChrJobParams`` row whose ``chrID`` is the character a monster drop
    recruits; ``DropSummonID`` names a Summon; and ``items`` is a four-slot
    ``ItemCode`` array in which ``code >> 8`` is the item and the low byte is a
    **rate, not a count** -- it takes values up to 100 across the recovered
    table, and 100 is a guaranteed drop rather than a hundred copies.

    A zero rate never rolls and is dropped here, which is the same reading the
    outcome catalog's own ceilings take.
    """
    jobs = chr_database.get("data")
    if not isinstance(jobs, list) or not jobs:
        raise DropCompendiumError("ChrDatabase must contain a nonempty data array")
    character_by_job: dict[int, int] = {}
    for job in jobs:
        if not isinstance(job, dict) or type(job.get("ID")) is not int or type(job.get("chrID")) is not int:
            raise DropCompendiumError("ChrJobParams row has an invalid ID or chrID")
        character_by_job[job["ID"]] = job["chrID"]

    rows = enemy_data.get("data")
    if not isinstance(rows, list) or not rows:
        raise DropCompendiumError("EnemyData must contain a nonempty data array")
    profiles: dict[int, dict[str, Any]] = {}
    for row in rows:
        required = ("ID", "DropBuddyID", "DropBuddyRatio", "DropJobID", "DropRatio", "items", "LV")
        if not isinstance(row, dict) or any(field not in row for field in required):
            raise DropCompendiumError("EnemyData record has missing required fields")
        items = []
        slots = row["items"]
        if not isinstance(slots, list):
            raise DropCompendiumError("EnemyData record has an invalid items array")
        for slot in slots:
            code = slot.get("code") if isinstance(slot, dict) else slot
            if type(code) is not int or code < 0:
                raise DropCompendiumError("EnemyData item slot has an invalid code")
            item_id, rate = code >> 8, code & 0xFF
            if item_id > 0 and rate > 0:
                items.append({"item_id": item_id, "rate": rate})
        job_id, job_rate = row["DropJobID"], float(row["DropRatio"])
        character_id = character_by_job.get(job_id, 0)
        summon_id, summon_rate = row.get("DropSummonID", 0), float(row.get("DropSummonRatio", 0.0))
        profiles[row["ID"]] = {
            "name": enemy_names.get(row["ID"], f"Enemy {row['ID']}"),
            "level": row["LV"],
            "companion": {"id": row["DropBuddyID"], "rate": float(row["DropBuddyRatio"])}
            if row["DropBuddyID"] > 0 and float(row["DropBuddyRatio"]) > 0 else None,
            "character": {"id": character_id, "rate": job_rate}
            if job_id > 0 and job_rate > 0 and character_id > 0 else None,
            "summon": {"id": summon_id, "rate": summon_rate}
            if type(summon_id) is int and summon_id > 0 and summon_rate > 0 else None,
            "items": items,
        }
    return profiles


def stage_metadata(battledata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Project each BattleData section slot into the fields the page renders.

    A slot is a stage only when ``battleCnt`` is nonzero; the rest are padding
    the client never offers.  They are carried here with ``has_battle`` false so
    the caller can exclude them deliberately rather than by forgetting to.
    """
    chapters = battledata.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise DropCompendiumError("BattleData must contain a nonempty chapters array")
    stages: dict[str, dict[str, Any]] = {}
    for chapter in chapters:
        if not isinstance(chapter, dict) or type(chapter.get("chapterNo")) is not int or not isinstance(chapter.get("sections"), list):
            raise DropCompendiumError("BattleData chapter is invalid")
        number = chapter["chapterNo"]
        for index, section in enumerate(chapter["sections"], start=1):
            if not isinstance(section, dict):
                raise DropCompendiumError("BattleData section must be an object")
            fields = ("rawStamina", "coins", "battleCnt", "itemID", "itemCount", "assumedLevel")
            if any(type(section.get(field)) is not int for field in fields):
                raise DropCompendiumError("BattleData section has invalid numeric metadata")
            allowed = []
            entries = section.get("dropBuddies", [])
            if not isinstance(entries, list):
                raise DropCompendiumError("BattleData section has an invalid dropBuddies list")
            for entry in entries:
                code = entry.get("code") if isinstance(entry, dict) else entry
                if type(code) is not int or code <= 0:
                    raise DropCompendiumError("BattleData dropBuddies entry is invalid")
                if code >> 8 > 0 and code & 0xFF > 0:
                    allowed.append({"companion_id": code >> 8, "cap": code & 0xFF})
            stages[f"{number}-{index}"] = {
                "chapter": number, "section": index,
                "family": family_of(number),
                "has_battle": section["battleCnt"] > 0,
                "battle_count": section["battleCnt"],
                "stamina": section["rawStamina"],
                "coins": section["coins"],
                "assumed_level": section["assumedLevel"],
                "clear_item": {"item_id": section["itemID"], "count": section["itemCount"]}
                if section["itemID"] > 0 and section["itemCount"] > 0 else None,
                "drop_buddies": allowed,
            }
    return stages


def _encounter_index(native: dict[str, Any], scenario: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for source, document in (("native", native), ("scenario", scenario)):
        if document is None:
            continue
        rows = document.get("stages")
        if not isinstance(rows, list):
            raise DropCompendiumError("encounter map has no stages array")
        for stage in rows:
            if not isinstance(stage, dict) or type(stage.get("chapter")) is not int or type(stage.get("section")) is not int:
                raise DropCompendiumError("encounter map has an invalid stage")
            index.setdefault(f"{stage['chapter']}-{stage['section']}", {
                "source": source,
                "spawns": stage.get("spawns", []),
            })
    return index


def build_payload(
    battledata: dict[str, Any],
    enemy_data: dict[str, Any],
    chr_database: dict[str, Any],
    native: dict[str, Any],
    scenario: dict[str, Any] | None,
    names: dict[str, Any] | None,
    enemy_names: dict[int, str],
    apk_label: str,
    outcome_catalog: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Return ``(payload, notes)`` for the renderer."""
    profiles = enemy_drop_profiles(enemy_data, chr_database, enemy_names)
    sections = stage_metadata(battledata)
    encounters = _encounter_index(native, scenario)

    # Imported, not restated: the compendium must withhold exactly what the
    # outcome catalog withholds, or it would describe a server that does not
    # exist.
    encounter_stages = [
        {"chapter": int(key.split("-")[0]), "section": int(key.split("-")[1])}
        for key in encounters
    ]
    aligned, refused = chapters_whose_sections_align(battledata, encounter_stages)

    labels = names or {}
    characters = labels.get("characters", {})
    companions = labels.get("companions", {})
    items = labels.get("items", {})

    def label(kind: str, ident: int) -> str:
        table = {"companion": companions, "character": characters, "item": items}.get(kind)
        if table is None:
            return f"Summon {ident}"
        return table.get(str(ident)) or f"{kind.title()} {ident}"

    stages: dict[str, dict[str, Any]] = {}
    raw_maxima: dict[str, dict[str, dict[int, int]]] = {}
    index: dict[tuple[str, int], dict[str, Any]] = defaultdict(lambda: {"stages": []})
    for key, meta in sorted(sections.items(), key=lambda kv: (kv[1]["chapter"], kv[1]["section"])):
        if not meta["has_battle"]:
            continue
        encounter = encounters.get(key) if meta["chapter"] in aligned else None
        companion_max: dict[int, int] = defaultdict(int)
        item_max: dict[int, int] = defaultdict(int)
        character_max: dict[int, int] = defaultdict(int)
        joined, inferred = False, False
        spawns: list[dict[str, Any]] = []
        if encounter is not None:
            joined = True
            for spawn in encounter["spawns"]:
                enemy = profiles.get(spawn.get("enemy_id")) if type(spawn.get("enemy_id")) is int else None
                if enemy is None:
                    joined = False
                    break
                if not spawn.get("exact", True):
                    inferred = True
                count = spawn.get("count", 0)
                spawns.append({
                    "e": spawn["enemy_id"], "n": enemy["name"], "c": count, "x": bool(spawn.get("exact", True)),
                })
                if enemy["companion"]:
                    companion_max[enemy["companion"]["id"]] += count
                if enemy["character"]:
                    character_max[enemy["character"]["id"]] += count
                for item in enemy["items"]:
                    item_max[item["item_id"]] += count
            if not joined:
                companion_max, item_max, character_max, spawns, inferred = (
                    defaultdict(int), defaultdict(int), defaultdict(int), [], False,
                )

        merged = dict(companion_max)
        for row in meta["drop_buddies"]:
            merged[row["companion_id"]] = max(merged.get(row["companion_id"], 0), row["cap"])

        base = {
            "stage": key, "chapter": meta["chapter"], "section": meta["section"],
            "family": meta["family"], "stamina": meta["stamina"],
        }
        for spawn in spawns:
            enemy = profiles[spawn["e"]]
            rows: list[tuple[str, int, float]] = []
            if enemy["companion"]:
                rows.append(("companion", enemy["companion"]["id"], enemy["companion"]["rate"]))
            if enemy["character"]:
                rows.append(("character", enemy["character"]["id"], enemy["character"]["rate"]))
            if enemy["summon"]:
                rows.append(("summon", enemy["summon"]["id"], enemy["summon"]["rate"]))
            for item in enemy["items"]:
                rows.append(("item", item["item_id"], float(item["rate"])))
            for kind, ident, rate in rows:
                ceiling = {"companion": merged, "item": item_max, "character": character_max}.get(kind, {}).get(ident)
                index[(kind, ident)]["stages"].append({
                    **base, "via": "enemy", "enemy": enemy["name"], "enemy_level": enemy["level"],
                    "rate": rate, "spawn_count": spawn["c"], "exact": spawn["x"], "ceiling": ceiling,
                })
        for row in meta["drop_buddies"]:
            entry = index[("companion", row["companion_id"])]
            if not any(s["stage"] == key and s["via"] == "enemy" for s in entry["stages"]):
                entry["stages"].append({
                    **base, "via": "section", "enemy": None, "enemy_level": None,
                    "rate": None, "spawn_count": None, "exact": True, "ceiling": row["cap"],
                })
        if meta["clear_item"]:
            index[("item", meta["clear_item"]["item_id"])]["stages"].append({
                **base, "via": "clear", "enemy": None, "enemy_level": None, "rate": 100.0,
                "spawn_count": meta["clear_item"]["count"], "exact": True,
                "ceiling": meta["clear_item"]["count"],
            })

        raw_maxima[key] = {
            "companion_maxima": dict(merged),
            "item_maxima": dict(item_max),
            "character_maxima": dict(character_max),
        }
        stages[key] = {
            "ch": meta["chapter"], "se": meta["section"], "fam": meta["family"],
            "st": meta["stamina"], "bc": meta["battle_count"], "co": meta["coins"],
            "lv": meta["assumed_level"], "j": joined, "inf": inferred, "sp": spawns,
            "ci": {**meta["clear_item"], "name": label("item", meta["clear_item"]["item_id"])}
            if meta["clear_item"] else None,
            "comp": {label("companion", k): v for k, v in sorted(merged.items())},
            "item": {label("item", k): v for k, v in sorted(item_max.items())},
            "char": {label("character", k): v for k, v in sorted(character_max.items())},
        }

    drops = []
    for (kind, ident), entry in index.items():
        rates = [row["rate"] for row in entry["stages"] if row["rate"] is not None]
        drops.append({
            "kind": kind, "id": ident, "name": label(kind, ident),
            "stage_count": len(entry["stages"]),
            "families": sorted({row["family"] for row in entry["stages"]}),
            "best_rate": max(rates) if rates else None,
            "stages": entry["stages"],
        })
    drops.sort(key=lambda row: (row["kind"], row["name"].lower()))

    by_family: dict[str, dict[str, int]] = defaultdict(lambda: {"stages": 0, "joined": 0})
    for stage in stages.values():
        by_family[stage["fam"]]["stages"] += 1
        by_family[stage["fam"]]["joined"] += 1 if stage["j"] else 0

    notes = _compare_with_catalog(raw_maxima, outcome_catalog) if outcome_catalog else []
    coverage = {
        "stages": len(stages),
        "joined": sum(1 for stage in stages.values() if stage["j"]),
        "unjoined": sum(1 for stage in stages.values() if not stage["j"]),
        "inferred": sum(1 for stage in stages.values() if stage["inf"]),
        "enemies_total": len(profiles),
        "enemies_with_drop": sum(
            1 for profile in profiles.values()
            if profile["companion"] or profile["character"] or profile["summon"] or profile["items"]
        ),
        "drops": {kind: sum(1 for row in drops if row["kind"] == kind)
                  for kind in ("companion", "character", "item", "summon")},
        "withheld_chapters": sorted(refused),
        "by_family": dict(sorted(by_family.items(), key=lambda kv: -kv[1]["stages"])),
    }
    return {
        "schema_version": SCHEMA_VERSION, "apk": apk_label,
        "coverage": coverage, "drops": drops, "stages": stages,
        "catalog_agreement": "not checked" if not outcome_catalog else ("exact" if not notes else "disagrees"),
    }, notes


def _compare_with_catalog(
    raw_maxima: dict[str, dict[str, dict[int, int]]], catalog: dict[str, Any],
) -> list[str]:
    """Report every stage where this page and the generated catalog disagree.

    Both are derived from the same records by the same rules, so a difference is
    a defect in one of them.  It is reported rather than rendered: a page that
    silently disagreed with the server it describes would be worse than one that
    admits it cannot be trusted.

    Only stages present in both are compared.  The catalog also carries the
    padding slots this page excludes, and this page carries Chapter 1, which the
    catalog's own generator skips; neither is a disagreement.
    """
    rules = {f"{row['chapter']}-{row['section']}": row for row in catalog.get("stages", [])}
    notes: list[str] = []
    for key, mine in sorted(raw_maxima.items()):
        rule = rules.get(key)
        if rule is None:
            continue
        for field, values in mine.items():
            theirs = {int(ident): count for ident, count in rule.get(field, {}).items()}
            if values != theirs:
                notes.append(f"stage {key} {field}: catalog {theirs}, page {values}")
    return notes


#: The page's whole presentation. Inlined rather than served beside the file so
#: the compendium stays one self-contained document an operator can move, mail,
#: or open from a phone with no server running.
_CSS = """
:root{
  --ink:#0d0e0c; --ink2:#14160f; --panel:#191c14; --panel2:#20241a;
  --edge:#33381f; --edge2:#4a5130;
  --parch:#ebe4d0; --parch-dim:#a9a48f; --parch-faint:#6f6c5e;
  --brass:#d4a83c; --brass-dim:#8d7228;
  --verd:#7fb894; --ember:#d97a45; --ash:#7a7768;
  --shadow:0 1px 0 rgba(255,255,255,.03), 0 8px 30px rgba(0,0,0,.6);
  --serif:"Iowan Old Style","Hoefler Text",Palatino,"Palatino Linotype",Georgia,serif;
  --sans:"Avenir Next Condensed","Avenir Next","Helvetica Neue",Helvetica,sans-serif;
  --mono:"SF Mono",Menlo,"Roboto Mono",monospace;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  background:
    radial-gradient(1200px 700px at 50% -10%, #1e2216 0%, transparent 60%),
    linear-gradient(180deg,#0d0e0c 0%,#101208 55%,#0b0c08 100%);
  background-attachment:fixed;
  color:var(--parch); font-family:var(--serif);
  font-size:16px; line-height:1.6; letter-spacing:.005em;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1180px;margin:0 auto;padding:0 24px 96px}

/* ---- masthead ---- */
header.mast{padding:64px 0 30px;border-bottom:1px solid var(--edge);position:relative}
header.mast:after{content:"";position:absolute;left:0;right:0;bottom:-3px;height:1px;background:linear-gradient(90deg,transparent,var(--brass-dim),transparent);opacity:.5}
.eyebrow{font-family:var(--sans);text-transform:uppercase;letter-spacing:.34em;font-size:11px;color:var(--brass);margin-bottom:18px}
h1{font-size:clamp(38px,6vw,62px);line-height:1.02;margin:0 0 14px;font-weight:400;letter-spacing:-.02em}
h1 em{font-style:italic;color:var(--brass)}
.dek{max-width:66ch;color:var(--parch-dim);font-size:17px;margin:0}
/* ---- controls ---- */
.controls{position:sticky;top:0;z-index:20;background:linear-gradient(180deg,#0f110b 72%,rgba(15,17,11,0));
          padding:18px 0 22px;margin-top:34px}
.tabs{display:flex;gap:2px;margin-bottom:14px}
.tab{font-family:var(--sans);text-transform:uppercase;letter-spacing:.16em;font-size:11px;
     padding:9px 16px;border:1px solid var(--edge);background:var(--panel);color:var(--parch-dim);
     cursor:pointer;transition:all .16s ease}
.tab:hover{color:var(--parch);border-color:var(--edge2)}
.tab[aria-selected="true"]{background:var(--brass);color:#14160f;border-color:var(--brass);font-weight:600}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
input[type=search]{flex:1 1 300px;min-width:0;background:var(--ink2);border:1px solid var(--edge2);
  color:var(--parch);font-family:var(--serif);font-size:16px;padding:11px 14px;border-radius:2px;outline:none}
input[type=search]:focus{border-color:var(--brass-dim);box-shadow:0 0 0 3px rgba(212,168,60,.09)}
input[type=search]::placeholder{color:var(--parch-faint)}
select{background:var(--ink2);border:1px solid var(--edge2);color:var(--parch-dim);font-family:var(--sans);
  text-transform:uppercase;letter-spacing:.1em;font-size:11px;padding:11px 10px;border-radius:2px;outline:none;cursor:pointer}
.count{font-family:var(--mono);font-size:11.5px;color:var(--parch-faint);white-space:nowrap}

/* ---- entries ---- */
.entry{border:1px solid var(--edge);border-top:none;background:var(--panel);
       animation:rise .4s ease backwards}
.entry:first-child{border-top:1px solid var(--edge)}
@keyframes rise{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:none}}
.head{display:grid;grid-template-columns:1fr auto;gap:14px;align-items:center;padding:14px 18px;
      cursor:pointer;transition:background .15s ease}
.head:hover{background:var(--panel2)}
.entry[open] .head{background:var(--panel2);border-bottom:1px solid var(--edge)}
.nm{font-size:19px;display:flex;align-items:center;gap:11px;flex-wrap:wrap}
.kind{font-family:var(--sans);text-transform:uppercase;letter-spacing:.15em;font-size:9.5px;
      padding:3px 8px;border:1px solid currentColor;border-radius:2px;opacity:.85}
.k-companion{color:#8fb4d4} .k-character{color:#c9a0d4} .k-item{color:var(--brass)} .k-summon{color:var(--verd)}
.meta{font-family:var(--mono);font-size:11.5px;color:var(--parch-faint);text-align:right;white-space:nowrap}
.meta b{color:var(--brass);font-weight:400}
.body{padding:4px 18px 18px}

table{width:100%;border-collapse:collapse;font-size:13.5px}
th{font-family:var(--sans);text-transform:uppercase;letter-spacing:.13em;font-size:9.5px;
   color:var(--parch-faint);text-align:left;padding:10px 10px 8px;border-bottom:1px solid var(--edge2);font-weight:400}
td{padding:8px 10px;border-bottom:1px solid rgba(51,56,31,.5);vertical-align:top}
tr:last-child td{border-bottom:none}
td.num{font-family:var(--mono);font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}
td.stage{font-family:var(--mono);color:var(--brass);white-space:nowrap}
.scroll{overflow-x:auto}
.fam{color:var(--parch-faint);font-size:12.5px}

.badge{font-family:var(--sans);text-transform:uppercase;letter-spacing:.1em;font-size:9px;
       padding:2px 7px;border-radius:2px;white-space:nowrap;border:1px solid currentColor}
.b-confirmed{color:var(--verd)} .b-inferred{color:var(--ember)} .b-list{color:var(--ash)} .b-clear{color:var(--brass)}

.empty{padding:60px 20px;text-align:center;color:var(--parch-faint);font-style:italic}

.floor{margin:0 0 14px;padding:10px 13px;border-left:2px solid var(--ember);
       background:rgba(217,122,69,.07);color:var(--parch-dim);font-size:13px;line-height:1.5}
.floor strong{color:var(--ember);font-weight:600}

/* ---- prose ---- */
.prose{max-width:74ch;margin-top:36px}
.prose h2{font-size:27px;font-weight:400;margin:44px 0 12px;letter-spacing:-.01em}
.prose h3{font-family:var(--sans);text-transform:uppercase;letter-spacing:.18em;font-size:11.5px;
          color:var(--brass);margin:32px 0 10px}
.prose p{color:var(--parch-dim);margin:0 0 15px}
.prose li{color:var(--parch-dim);margin-bottom:9px}
.prose code{font-family:var(--mono);font-size:12.5px;color:var(--brass);background:rgba(212,168,60,.07);
            padding:1px 5px;border-radius:2px}
.note{border-left:2px solid var(--brass-dim);padding:4px 0 4px 18px;margin:22px 0;color:var(--parch-dim)}
.ftable{width:100%;border-collapse:collapse;margin:18px 0;font-size:13.5px}
.ftable th,.ftable td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--edge)}
.ftable td.num{text-align:right}
footer{margin-top:70px;padding-top:26px;border-top:1px solid var(--edge);
       font-family:var(--mono);font-size:11px;color:var(--parch-faint)}
@media(max-width:640px){
  .head{grid-template-columns:1fr;gap:7px}
  .meta{text-align:left}
  .wrap{padding:0 16px 60px}
}
"""

#: Rendering and filtering run in the page from one embedded JSON payload; there
#: is no build step and no network access, which is what keeps it openable from
#: `file://` years from now.
_JS = r"""
const DATA = JSON.parse(document.getElementById('payload').textContent);
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const pct = r => r === null || r === undefined ? '—' : (Number.isInteger(r) ? r : r.toFixed(2).replace(/0+$/,'').replace(/\.$/,'')) + '%';

let tab = 'drops';

function badge(s){
  if (s.via === 'section') return '<span class="badge b-list">list only</span>';
  if (s.via === 'clear')   return '<span class="badge b-clear">clear reward</span>';
  return s.exact ? '<span class="badge b-confirmed">confirmed</span>'
                 : '<span class="badge b-inferred">inferred</span>';
}

function dropRows(d){
  const rows = d.stages.map(s => `<tr>
    <td class="stage">${esc(s.stage)}</td>
    <td class="fam">${esc(s.family)}</td>
    <td>${s.enemy ? esc(s.enemy) + (s.enemy_level ? ` <span class="fam">Lv ${s.enemy_level}</span>` : '') : '<span class="fam">—</span>'}</td>
    <td class="num">${pct(s.rate)}</td>
    <td class="num">${s.spawn_count ?? '—'}</td>
    <td class="num">${s.ceiling ?? '—'}</td>
    <td class="num">${s.stamina}</td>
    <td>${badge(s)}</td></tr>`).join('');
  return floorNote(d) + `<div class="scroll"><table>
    <thead><tr><th>Stage</th><th>Family</th><th>Dropped by</th><th>Rate</th>
    <th>Spawns</th><th>Cap</th><th>Stam</th><th>Basis</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

// A drop's stage list reads as a farming guide, so it has to say what it is.
// It is a floor: the stages that could be evidenced, not the stages that drop
// this. For an item or a character the gap is total rather than partial --
// an unjoined stage's only surviving evidence is its dropBuddies allowlist,
// which names Companions and nothing else -- so those two kinds cannot be
// evidenced from an unjoined stage even in principle.
function floorNote(d){
  const c = DATA.coverage, blind = c.unjoined, total = c.stages;
  const kindNote = (d.kind === 'item' || d.kind === 'character')
    ? `No ${d.kind} drop can be evidenced from any of them, because the only evidence an
       unjoined stage carries is its Companion allowlist.`
    : `Their section allowlists still speak, but no rate and no spawn count survives for them.`;
  return `<div class="floor"><strong>This list is a floor, not a census.</strong>
    ${blind} of ${total} stages have no usable encounter map. ${kindNote}
    A stage missing below has not been ruled out &mdash; it has not been looked at.</div>`;
}

function stageRows(key, s){
  const sec = (label, obj, cls) => {
    const keys = Object.keys(obj);
    if (!keys.length) return '';
    return `<tr><td class="fam">${label}</td><td>${keys.sort().map(k =>
      `<span class="${cls}">${esc(k)}</span> <span class="fam">×${obj[k]}</span>`).join(' &nbsp;·&nbsp; ')}</td></tr>`;
  };
  let out = `<div class="scroll"><table><tbody>`;
  out += sec('Companions', s.comp, 'k-companion');
  out += sec('Items', s.item, 'k-item');
  out += sec('Characters', s.char, 'k-character');
  if (s.ci) out += `<tr><td class="fam">Clear reward</td><td><span class="k-item">${esc(s.ci.name)}</span> <span class="fam">×${s.ci.count} (guaranteed)</span></td></tr>`;
  if (s.sp.length) out += `<tr><td class="fam">Spawns</td><td>${s.sp.map(p =>
      `${esc(p.n)} <span class="fam">×${p.c}${p.x ? '' : ' (inferred)'}</span>`).join(' &nbsp;·&nbsp; ')}</td></tr>`;
  if (!s.j) out += `<tr><td class="fam">Encounters</td><td><span class="badge b-list">unresolved — contents unknown, not empty</span></td></tr>`;
  out += `</tbody></table></div>`;
  return out;
}

function render(){
  const q = $('#q').value.trim().toLowerCase();
  const fam = $('#fam').value, kind = $('#kind').value;
  const root = $('#list');

  if (tab === 'drops'){
    let items = DATA.drops.filter(d =>
      (!kind || d.kind === kind) &&
      (!fam || d.families.includes(fam)) &&
      (!q || d.name.toLowerCase().includes(q) ||
        d.stages.some(s => (s.enemy||'').toLowerCase().includes(q) || s.stage.includes(q))));
    $('#count').textContent = `${items.length} of ${DATA.drops.length} drops`;
    root.innerHTML = items.length ? items.slice(0, 400).map((d, i) => `
      <details class="entry" style="animation-delay:${Math.min(i,24)*11}ms">
        <summary class="head">
          <span class="nm">${esc(d.name)} <span class="kind k-${d.kind}">${d.kind}</span></span>
          <span class="meta">${d.stage_count} stage${d.stage_count===1?'':'s'}${d.best_rate!==null?` · best <b>${pct(d.best_rate)}</b>`:' · <b>no stated rate</b>'}</span>
        </summary>
        <div class="body">${dropRows(d)}</div>
      </details>`).join('') : '<div class="empty">Nothing matches that.</div>';
  } else {
    let keys = Object.keys(DATA.stages).filter(k => {
      const s = DATA.stages[k];
      if (fam && s.fam !== fam) return false;
      if (!q) return true;
      return k.includes(q) || s.fam.toLowerCase().includes(q) ||
        Object.keys(s.comp).concat(Object.keys(s.item), Object.keys(s.char)).some(n => n.toLowerCase().includes(q)) ||
        s.sp.some(p => (p.n||'').toLowerCase().includes(q));
    }).sort((a,b) => DATA.stages[a].ch - DATA.stages[b].ch || DATA.stages[a].se - DATA.stages[b].se);
    $('#count').textContent = `${keys.length} of ${Object.keys(DATA.stages).length} stages`;
    root.innerHTML = keys.length ? keys.slice(0, 400).map((k, i) => {
      const s = DATA.stages[k];
      const n = Object.keys(s.comp).length + Object.keys(s.item).length + Object.keys(s.char).length;
      return `<details class="entry" style="animation-delay:${Math.min(i,24)*11}ms">
        <summary class="head">
          <span class="nm">${esc(k)} <span class="kind k-${s.j?'summon':'item'}">${esc(s.fam)}</span></span>
          <span class="meta">${n} distinct drop${n===1?'':'s'} · ${s.st} stamina · ${s.bc} battle${s.bc===1?'':'s'}${s.j?'':' · <b>unresolved</b>'}</span>
        </summary>
        <div class="body">${stageRows(k, s)}</div>
      </details>`;
    }).join('') : '<div class="empty">Nothing matches that.</div>';
  }
}

document.querySelectorAll('.tab').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach(x => x.setAttribute('aria-selected', x === b));
  tab = b.dataset.tab;
  $('#kind').style.display = tab === 'drops' ? '' : 'none';
  render();
}));
['#q','#fam','#kind'].forEach(s => $(s).addEventListener('input', render));

const fams = [...new Set(Object.values(DATA.stages).map(s => s.fam))].sort();
$('#fam').innerHTML = '<option value="">All families</option>' +
  fams.map(f => `<option value="${esc(f)}">${esc(f)}</option>`).join('');
render();
"""


def render(payload: dict[str, Any], notes: list[str] | None = None) -> str:
    """Render one self-contained HTML document from a built payload."""
    coverage = payload["coverage"]
    # `</` inside a script block would close it early, whatever the JSON says.
    blob = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    families = "".join(
        f'<tr><td>{escape(name)}</td><td class="num">{value["stages"]}</td>'
        f'<td class="num">{value["joined"]}</td>'
        f'<td class="num">{value["stages"] - value["joined"]}</td></tr>'
        for name, value in coverage["by_family"].items()
    )
    withheld = coverage["withheld_chapters"]
    note_block = ""
    if notes:
        rows = "".join(f"<li>{escape(note)}</li>" for note in notes[:40])
        note_block = (
            '<h2>Disagreements with the generated catalog</h2>'
            '<p>These stages differ between this page and the catalog the server enforces. '
            'Both are derived from the same records by the same rules, so each one is a defect '
            'in one of them.</p>'
            f'<ul>{rows}</ul>'
        )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Drop Compendium &mdash; Project Liminal Gate</title>
<style>{_CSS}</style></head>
<body><div class="wrap">

<header class="mast">
  <div class="eyebrow">Project Liminal Gate &middot; Field Reference</div>
  <h1>The Drop <em>Compendium</em></h1>
  <p class="dek">Every Companion, character, and item this client can yield &mdash; what drops it,
  where it spawns, at what rate the recovered table states, and how far each claim is actually
  evidenced. Derived entirely from your own reviewed APK.</p>
</header>

<div class="controls">
  <div class="tabs">
    <button class="tab" data-tab="drops" aria-selected="true">By drop</button>
    <button class="tab" data-tab="stages" aria-selected="false">By stage</button>
  </div>
  <div class="row">
    <input type="search" id="q" placeholder="Search a Companion, character, item, enemy, or stage&hellip;" autocomplete="off">
    <select id="kind">
      <option value="">All kinds</option>
      <option value="companion">Companions</option>
      <option value="character">Characters</option>
      <option value="item">Items</option>
      <option value="summon">Summons</option>
    </select>
    <select id="fam"></select>
    <span class="count" id="count"></span>
  </div>
</div>

<div id="list"></div>

<div class="prose">
<h2>How to read this</h2>

<p>Each drop lists every stage that can yield it. The <strong>Basis</strong> column is the part
worth reading carefully, because its four values mean genuinely different things.</p>

<h3>Confirmed</h3>
<p>The stage's compiled battle program was disassembled, every spawn resolved to an
<code>EnemyData</code> record, and that record names the drop. The rate is the client's own
<code>DropBuddyRatio</code>, <code>DropRatio</code>, or item-slot rate byte, as a percentage.</p>

<h3>Inferred</h3>
<p>The same join, but at least one spawn resolved to a <em>variant</em> initializer &mdash; a base
enemy carrying a behavioural or positional modifier. The base enemy's drops are read through,
which is strongly supported but not proven for that exact spawn.</p>

<h3>List only</h3>
<p>The drop comes from the stage's own <code>BattleData.Section.dropBuddies</code> allowlist. That
states a per-clear <strong>cap</strong> and no rate at all, so the Rate column stays blank. For
every stage outside the core story this is usually the only evidence there is.</p>

<h3>Clear reward</h3>
<p>The section's <code>itemID</code>/<code>itemCount</code>: a guaranteed award on completion,
not a roll.</p>

<div class="note">A blank rate is not a low rate. It means the recovered data states a cap
without stating odds, and nothing here invents the difference.</div>

<h2>What this does not know</h2>

<p>{coverage["unjoined"]} of {coverage["stages"]} playable stages have no usable encounter map. For
those, an absent drop means <strong>unknown</strong>, never <strong>none</strong> &mdash; the
section allowlist is all that speaks, and it only ever lists Companions. That last clause is the
one to hold on to: an <em>item</em> or <em>character</em> can only ever be evidenced from a stage
whose encounter map resolved, so for those two kinds every unjoined stage is silent by
construction rather than by measurement. Four causes, and all but one are limits of the data
rather than of effort:</p>

<ul>
<li><strong>No enemy rows.</strong> Spawn symbols that resolve to enemy IDs carrying no
<code>EnemyData</code> record. This is the chapter 38&ndash;42 gap, and it is the normal condition
outside the core story: the client ships the battle <em>programs</em> for the event, Eidolon,
Descent, Tower and Melting Pot chapters without shipping their enemy <em>data</em>. Nothing
recovers a row that was never in the APK.</li>
<li><strong>Section skew ({len(withheld)} chapters).</strong> A chapter's compiled program numbers
its generators independently of <code>BattleData</code>. Chapter 2000 declares four sections and
compiles generators numbered 1, 3, 5 and 7. Reading those numbers as section numbers would file
one section's spawns under another, so such chapters are withheld rather than guessed at &mdash;
a wrong ceiling is worse than a missing one, because a ceiling decides whether a legitimate clear
is refused. Compiling <em>fewer</em> generators than a chapter declares is not skew and is not
withheld.</li>
<li><strong>No battle program.</strong> A chapter class that compiles no generator for that section
at all. Metal Zone, the unbannered Tower copy, the Five Emperors side world and the tutorial are
wholly of this kind, and no amount of reading recovers a program the client does not contain. The
one recoverable case found so far was different in kind: the World Map Specials compile their
generators under quest names (<code>Battle_Shinen_1</code>) rather than section numbers, so they
read as absent until the importer learned that shape.</li>
<li><strong>Unrecognised variants.</strong> Symbols whose suffix chain reduces to no known base
enemy. This class looks tractable and is not. On the reviewed build a census of every one of them
found 37 distinct symbols across 41 stages; a <em>perfect</em> resolver &mdash; one allowed to reduce
each symbol to any real <code>Enemies</code> member at all &mdash; would join <strong>none</strong>
of those stages. Four reduce to a real member whose ID has no <code>EnemyData</code> record, and the
other 33 reduce to no member under any rule. The ceiling is structural: the enum names 1,932
enemies and only 992 of them have a record. Widening the suffix table would lower the unresolved
count on this page while adding no drop at all, which is worse than leaving it alone.</li>
</ul>

<table class="ftable">
<thead><tr><th>Family</th><th class="num">Stages</th><th class="num">Resolved</th><th class="num">Unresolved</th></tr></thead>
<tbody>{families}</tbody></table>

<p>Padding matters too: a <code>BattleData</code> slot is a stage only when its
<code>battleCnt</code> is nonzero. The empty slots are excluded here, including all nine of
Chapter 20's phantom sections &mdash; some of which carry a <code>dropBuddies</code> manifest
attached to a stage no player can reach.</p>

{note_block}

<h2>Why the numbers can be trusted</h2>

<p>This page is not an independent reading of the game data, and does not ask to be trusted as
one. It recomputes each stage's ceilings from the same records by the same rules the server's
<code>story_outcome_generator</code> uses, imports that generator's own section-skew rule rather
than restating it, and then compares every shared stage against the catalog the server actually
enforces. Any disagreement is printed above instead of being rendered as fact.</p>

<p>What this page adds over that catalog is precisely what the catalog discards: the drop rates,
the enemy identities, and the direction of the index.</p>

<footer>
Generated from a locally reviewed APK. Contains decoded game text and lives in the ignored data
directory &mdash; do not publish or commit it.<br>
Rates are the recovered table's stated values, not observed frequencies. No live-service capture
informs this page.
</footer>
</div>

</div>
<script id="payload" type="application/json">{blob}</script>
<script>{_JS}</script>
</body></html>
"""


def write_compendium(path: Path, html: str) -> None:
    """Write the rendered page, creating its directory if needed."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
    except OSError as error:
        raise DropCompendiumError(f"could not write the compendium: {path}") from error


def build_from_apk(
    apk: Path,
    dummy_dll_dir: Path,
    native: dict[str, Any],
    scenario: dict[str, Any] | None,
    names: dict[str, Any] | None,
    outcome_catalog: dict[str, Any] | None = None,
    trees: dict[str, Any] | None = None,
) -> tuple[str, list[str], dict[str, Any]]:
    """Build the page from a reviewed APK. Returns ``(html, notes, payload)``.

    ``trees`` lets a caller that has already paid for the type-tree build hand
    it over; that load is the slow part of every importer here and doing it a
    second time during guided setup would be pure waste.
    """
    if trees is None:
        trees = load_master_trees(apk, dummy_dll_dir, ("BattleData", "EnemyData", "ChrDatabase"))
    for required in ("BattleData", "EnemyData", "ChrDatabase"):
        if required not in trees:
            raise DropCompendiumError(f"the compendium needs the {required} master object")
    enemy_names: dict[int, str] = {}
    try:
        with zipfile.ZipFile(apk) as archive:
            enemy_names = decode_enemy_names(trees["EnemyData"], load_inverse_table(archive.read(IL2CPP_METADATA_MEMBER)))
    except (OSError, KeyError, zipfile.BadZipFile, MasterStringError):
        # Bare enemy IDs are a poorer page, not a wrong one.
        enemy_names = {}
    payload, notes = build_payload(
        trees["BattleData"], trees["EnemyData"], trees["ChrDatabase"],
        native, scenario, names, enemy_names, apk.name, outcome_catalog,
    )
    return render(payload, notes), notes, payload


def _read(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DropCompendiumError(f"could not read {what}: {path}") from error


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apk", required=True, type=Path, help="your own reviewed APK")
    parser.add_argument("--dummy-dll-dir", required=True, type=Path, help="locally generated DummyDll directory")
    parser.add_argument("--native-encounters", required=True, type=Path, help="native_encounter_importer output")
    parser.add_argument("--scenario-encounters", type=Path, help="scenario_encounter_importer output")
    parser.add_argument("--names", type=Path, help="names.json, so drops read as names rather than IDs")
    parser.add_argument("--story-outcome-catalog", type=Path, help="the generated catalog to check this page against")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--force", action="store_true", help="overwrite an existing output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output.exists() and not args.force:
        print(f"refusing to overwrite {args.output}; pass --force")
        return 1
    try:
        html, notes, payload = build_from_apk(
            args.apk, args.dummy_dll_dir,
            _read(args.native_encounters, "the native encounter map"),
            _read(args.scenario_encounters, "the scenario encounter map") if args.scenario_encounters else None,
            _read(args.names, "the local name table") if args.names else None,
            _read(args.story_outcome_catalog, "the story-outcome catalog") if args.story_outcome_catalog else None,
        )
        write_compendium(args.output, html)
    except DropCompendiumError as error:
        print(f"could not build the drop compendium: {error}")
        return 1
    coverage = payload["coverage"]
    print(f"wrote the local drop compendium -> {args.output}")
    print(
        f"  {len(payload['drops'])} distinct drop(s) across {coverage['stages']} playable stage(s); "
        f"{coverage['joined']} stage(s) have a resolved encounter map"
    )
    if payload["catalog_agreement"] == "exact":
        print("  agrees with the generated story-outcome catalog on every shared stage")
    for note in notes[:10]:
        print(f"  disagreement: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
