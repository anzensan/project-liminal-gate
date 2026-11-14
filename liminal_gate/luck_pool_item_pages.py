"""Reading the community record's item pages as a second source of chest pools.

The record documents Luck Treasure Chests from two directions that were never
reconciled. A stage page lists what its chests pay, but only for some stages.
An item page lists where the item drops, and says "Luck Treasure Chests (D,
Luck 100)" under a stage the stage's own page never mentions. A tester found
the second kind on issue 107: the Heartwood Sword is documented to drop from
Story 20-1, whose stage page carries no chest table, so the server rolled a
donated chest that could never contain it.

This module is the inverted index. It reads item-page wikitext, extracts every
chest claim, and does two things with them:

* ``generate`` writes :mod:`liminal_gate.luck_pool_item_page_data`, the claims
  that name an exact stage and tier. Those are facts about one cell of one
  pool, and they are added to that cell rather than replacing the stage.
* ``audit`` compares every claim, whatever family it names, with the bundled
  pools, so the next page family nobody imported shows up as a diff and not as
  a tester report.

Parsing is strict. A line that mentions a chest but does not match a known
shape fails the run, because a silently skipped claim is exactly the gap this
exists to close.

Usage::

    python -m liminal_gate.luck_pool_item_pages fetch  --out pages.json
    python -m liminal_gate.luck_pool_item_pages audit  --pages pages.json --names names.json
    python -m liminal_gate.luck_pool_item_pages generate --pages pages.json --names names.json
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
import unicodedata
import urllib.parse
import urllib.request

from liminal_gate.luck_pool_catalog import TIER_NAMES
from liminal_gate.luck_pool_data import DOCUMENTED_CHEST_POOLS, pool_for, refuses_chest
from liminal_gate.luck_pool_item_page_data import ITEM_PAGE_CHEST_CELLS

WIKI_API = "https://terrabattle.fandom.com/api.php"
#: Every item page transcludes this template, so the transclusion list is the
#: complete item set. A text search for "Luck Treasure Chests" is not: it
#: silently missed the Heartwood Sword.
PAGE_TEMPLATES = {
    "items": "Template:Item",
    "characters": "Template:Character",
    "companions": "Template:Companion",
}

_STAGE = re.compile(r"\{\{Story\|(\d+)\|(\d+)\}\}")
_CHEST = re.compile(r"Luck Treasure Chests?(?: \(([^)]*)\))?")
_HEADING = re.compile(r"^==\s*Drop locations\s*==\s*$", re.IGNORECASE)
_ANY_HEADING = re.compile(r"^==[^=].*==\s*$")
#: Item pages whose title carries a disambiguator the client's name does not.
_DISAMBIGUATOR = re.compile(r"\s+\((?:Item)\)$")


class ItemPageError(ValueError):
    """An item page carries a chest claim in a shape this parser does not know."""


@dataclass(frozen=True)
class ChestClaim:
    """One "this item drops from a Luck chest here" statement."""

    item: str
    label: str
    stage: tuple[int, int] | None
    tiers: tuple[str, ...]


def _parse_tiers(raw: str | None, where: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    tiers = tuple(part.strip() for part in raw.split(","))
    unknown = [tier for tier in tiers if tier not in TIER_NAMES]
    if unknown:
        raise ItemPageError(f"{where}: unknown chest tier {unknown[0]!r}")
    return tiers


def drop_section(text: str) -> list[str]:
    """The lines under the page's Drop locations heading, or none."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if _HEADING.match(line.strip()):
            end = next(
                (stop for stop in range(index + 1, len(lines)) if _ANY_HEADING.match(lines[stop].strip())),
                len(lines),
            )
            return lines[index + 1:end]
    return []


def parse_claims(item: str, text: str) -> list[ChestClaim]:
    """Every chest claim in one item page's drop section."""
    claims: list[ChestClaim] = []
    parent = ""
    for line in drop_section(text):
        if "Luck Treasure" not in line:
            if line.startswith("*") and not line.startswith("**"):
                parent = line
            continue
        match = _CHEST.search(line)
        where = f"{item}: {line.strip()!r}"
        if match is None:
            raise ItemPageError(f"{where}: mentions a chest in an unrecognized shape")
        tiers = _parse_tiers(match.group(1), where)
        child = line.startswith("**")
        # A child bullet belongs to the stage bullet above it; an inline claim
        # names its own stage on the same line.
        source = parent if child else line
        if child and not parent:
            raise ItemPageError(f"{where}: chest line has no stage line above it")
        stage = _STAGE.search(source)
        claims.append(ChestClaim(
            item=item, label=source.strip(),
            stage=(int(stage.group(1)), int(stage.group(2))) if stage else None,
            tiers=tiers,
        ))
        if not child:
            parent = line
    return claims


def resolve_items(names: dict, titles: list[str]) -> tuple[dict[str, str], list[str]]:
    """Item title -> item id, and the titles that did not resolve uniquely."""
    by_name: dict[str, list[str]] = defaultdict(list)
    for identifier, name in names["items"].items():
        by_name[name].append(identifier)
    resolved: dict[str, str] = {}
    unresolved: list[str] = []
    for title in titles:
        ids = by_name.get(_DISAMBIGUATOR.sub("", title), [])
        if len(ids) == 1:
            resolved[title] = ids[0]
        else:
            unresolved.append(title)
    return resolved, unresolved


def all_claims(pages: dict[str, dict]) -> list[ChestClaim]:
    claims: list[ChestClaim] = []
    for title in sorted(pages):
        claims.extend(parse_claims(title, pages[title]["text"]))
    return claims


def story_cells(
    claims: list[ChestClaim], ids: dict[str, str],
) -> dict[tuple[int, int], dict[str, tuple[str, ...]]]:
    """Claims that name an exact stage and tier, as pool cells in wire form."""
    cells: dict[tuple[int, int], dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    for claim in claims:
        if claim.stage is None or not claim.tiers or claim.item not in ids:
            continue
        for tier in claim.tiers:
            cells[claim.stage][tier].add(int(ids[claim.item]))
    return {
        stage: {
            tier: tuple(f"I{item}" for item in sorted(items))
            for tier, items in sorted(tiers.items(), key=lambda entry: TIER_NAMES.index(entry[0]))
        }
        for stage, tiers in sorted(cells.items())
    }


def _merged_pools() -> dict[tuple[int, int], dict[str, tuple[str, ...]]]:
    """The documented pools with item-page cells folded in, as `pool_for` answers."""
    stages = set(DOCUMENTED_CHEST_POOLS) | set(ITEM_PAGE_CHEST_CELLS)
    return {
        stage: {tier: pool_for(*stage, tier) for tier in TIER_NAMES if pool_for(*stage, tier)}
        for stage in stages
    }


#: Character and Companion pages name the quests that chest them but, unlike item
#: pages, carry no tier, so the most they can be held to is that the reward
#: appears in some bundled pool. These two are claimed from a quest this archive
#: cannot serve: Chaos I and Raijin I are the first quests of three-stage
#: Eidolons, and only the third has a battle behind it (see
#: `EIDOLON_THIRD_QUEST_REWARDS`). The other first- and second-quest Companions
#: are held by other families, which is why only these two surface.
UNSERVED_QUEST_REWARDS: dict[str, str] = {
    "O20": "Thunderous Wand: Raijin I, not served",
    "O26": "Sable Wand: Chaos I, not served",
}

_PEOPLE_KINDS = {"characters": ("M", "characters"), "companions": ("O", "companions")}
_PAGE_QUALIFIER = re.compile(r"\s+\((?:Companion|Character)\)$")


def _normal(name: str) -> str:
    """A name as the two sources spell it alike: Roman numeral glyphs and Greek
    capital Omicron folded to ASCII, and runs of spaces collapsed."""
    return " ".join(unicodedata.normalize("NFKC", name).replace("\u039f", "O").split())


def people_claims(corpus: dict, names: dict) -> tuple[list[tuple[str, str]], list[str]]:
    """(title, reward id) for each character or Companion page that names a chest
    source, and the titles that did not resolve to exactly one id."""
    claims: list[tuple[str, str]] = []
    unresolved: list[str] = []
    for kind, (prefix, table) in _PEOPLE_KINDS.items():
        by_name: dict[str, list[str]] = defaultdict(list)
        for identifier, name in names[table].items():
            by_name[_normal(name)].append(identifier)
        for title, page in sorted(corpus.get(kind, {}).items()):
            lines = [
                line for line in page["text"].splitlines()
                if "Luck Treasure Chest" in line and not line.lstrip("* ").startswith("Removed")
            ]
            if not lines:
                continue
            ids = by_name.get(_normal(_PAGE_QUALIFIER.sub("", title)), [])
            if len(ids) == 1:
                claims.append((title, f"{prefix}{ids[0]}"))
            else:
                unresolved.append(f"{kind[:-1]} page {title!r}")
    return claims, unresolved


def audit(pages: dict[str, dict], names: dict, corpus: dict | None = None) -> tuple[list[str], list[str]]:
    """Report lines, and the lines that mean the audit failed."""
    claims = all_claims(pages)
    titles = sorted({claim.item for claim in claims})
    ids, unresolved = resolve_items(names, titles)
    report: list[str] = []
    failures = [f"item name not uniquely in names.json: {title}" for title in unresolved]

    held: dict[str, set[str]] = defaultdict(set)
    for stage, tiers in _merged_pools().items():
        if refuses_chest(stage[0]):
            continue
        for tier, pool in tiers.items():
            for reward in pool:
                held[reward].add(tier)

    exact = story_cells(claims, ids)
    for stage, tiers in exact.items():
        for tier, rewards in tiers.items():
            for reward in rewards:
                if reward not in pool_for(*stage, tier):
                    report.append(f"MISSING  {stage[0]}-{stage[1]} {tier:8} {reward}  ({names['items'].get(reward[1:])})")

    for claim in claims:
        if claim.stage is not None or claim.item not in ids:
            continue
        reward = f"I{ids[claim.item]}"
        wanted = set(claim.tiers) if claim.tiers else set(TIER_NAMES)
        if not held.get(reward, set()) & wanted:
            report.append(
                f"NOWHERE  {claim.item} ({reward}) claimed for {sorted(wanted)} "
                f"under {claim.label!r}, and no bundled pool pays it in those tiers"
            )
    if corpus is not None:
        people, lost = people_claims(corpus, names)
        failures += [f"name not uniquely in names.json: {title}" for title in lost]
        for title, reward in people:
            if not held.get(reward) and reward not in UNSERVED_QUEST_REWARDS:
                report.append(f"NOWHERE  {title} ({reward}) names a chest source, and no bundled pool pays it")
    return sorted(set(report)), failures


def fetch(out: Path) -> int:
    """Download the wikitext and revision id of every item, character and Companion page."""
    def call(**params: object) -> dict:
        query = urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"})
        request = urllib.request.Request(f"{WIKI_API}?{query}", headers={"User-Agent": "liminal-gate-item-page-audit"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)

    def pages_of(template: str) -> dict[str, dict]:
        titles: list[str] = []
        token: dict = {}
        while True:
            reply = call(action="query", list="embeddedin", eititle=template, eilimit=500, einamespace=0, **token)
            titles += [row["title"] for row in reply["query"]["embeddedin"]]
            if "continue" not in reply:
                break
            token = {"eicontinue": reply["continue"]["eicontinue"]}
        pages: dict[str, dict] = {}
        for start in range(0, len(titles), 40):
            reply = call(
                action="query", prop="revisions", rvprop="ids|content", rvslots="main",
                titles="|".join(titles[start:start + 40]),
            )
            for page in reply["query"]["pages"]:
                revisions = page.get("revisions")
                if revisions:
                    pages[page["title"]] = {"rev": revisions[0]["revid"], "text": revisions[0]["slots"]["main"]["content"]}
        return pages

    corpus = {kind: pages_of(template) for kind, template in PAGE_TEMPLATES.items()}
    out.write_text(json.dumps(corpus, indent=1, sort_keys=True), encoding="utf-8")
    print("fetched " + ", ".join(f"{len(pages)} {kind}" for kind, pages in corpus.items()) + f" pages -> {out}")
    return 0


def render_data(pages: dict[str, dict], names: dict) -> str:
    """The data module for the exact-stage claims."""
    claims = all_claims(pages)
    ids, _ = resolve_items(names, sorted({claim.item for claim in claims}))
    cells = story_cells(claims, ids)
    sources: dict[tuple[int, int], list[str]] = defaultdict(list)
    for claim in claims:
        if claim.stage is not None and claim.tiers and claim.item in ids:
            sources[claim.stage].append(f"{claim.item} (rev {pages[claim.item]['rev']})")
    lines = [
        '"""Chest rewards the community record states on item pages, by exact stage and tier.',
        "",
        "Generated by ``python -m liminal_gate.luck_pool_item_pages generate``; do not edit",
        "by hand. Each cell is a reward the record says a stage's chest tier pays, taken",
        "from the item's own page. Cells are *added* to the stage's pool, never a",
        "replacement for it: the record names one item in the tier, not the whole tier.",
        "See ``luck_pool_data.pool_for`` and ``luck_pool_interpolation`` for how they",
        'merge. Issue 107.',
        '"""',
        "",
        "ITEM_PAGE_CHEST_CELLS: dict[tuple[int, int], dict[str, tuple[str, ...]]] = {",
    ]
    for stage, tiers in cells.items():
        lines.append(f"    # {', '.join(sorted(set(sources[stage])))}")
        body = ", ".join(f'"{tier}": ({", ".join(repr(r) for r in rewards)},)' for tier, rewards in tiers.items())
        lines.append(f"    {stage}: {{{body}}},")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("fetch").add_argument("--out", type=Path, required=True)
    for name in ("audit", "generate"):
        command = sub.add_parser(name)
        command.add_argument("--pages", type=Path, required=True)
        command.add_argument("--names", type=Path, required=True)
    sub.choices["generate"].add_argument(
        "--out", type=Path, default=Path(__file__).with_name("luck_pool_item_page_data.py"),
    )
    args = parser.parse_args(argv)
    if args.command == "fetch":
        return fetch(args.out)
    corpus = json.loads(args.pages.read_text(encoding="utf-8"))
    pages = corpus["items"]
    names = json.loads(args.names.read_text(encoding="utf-8"))
    if args.command == "generate":
        args.out.write_text(render_data(pages, names), encoding="utf-8")
        print(f"wrote {args.out}")
        return 0
    report, failures = audit(pages, names, corpus)
    for line in report:
        print(line)
    for line in failures:
        print(f"FAIL     {line}", file=sys.stderr)
    print(f"{len(report)} gap(s), {len(failures)} failure(s)")
    return 1 if report or failures else 0


if __name__ == "__main__":
    sys.exit(main())
