# Advanced local configuration

This page is for operators tightening or extending the guided core-story path.
The README quick start enables its built-in ordinary Chapter 2--42 progression
policy automatically. Each optional catalog stays local and is supplied by the
operator.

## Generating the `DummyDll` directory

Several optional features below need `--dummy-dll-dir`, and none of them can
work without it. It is a directory of stub .NET assemblies you generate from
your own copy of the game, and it exists for one reason: **the master data is
readable but its schema is not.**

`ChrDatabase`, `ItemSet`, and `BuddyDatabase` are Unity `MonoBehaviour` objects
inside `resources.assets`. A Unity build normally stores a *type tree* beside
serialized data saying which bytes are which field; an IL2CPP release build
strips it. What remains is an untyped blob. The field layout only exists in the
compiled code, so it has to be recovered from there before anything can read a
character or an item. That recovered layout is the `DummyDll` directory: class
and field definitions with no executable code.

### 1. Unpack the two inputs from your APK

An APK is a zip archive:

```sh
unzip -j local-input/terra-battle-5.5.7-170.apk \
  "lib/arm64-v8a/libil2cpp.so" \
  "assets/bin/Data/Managed/Metadata/global-metadata.dat" \
  -d il2cpp-input
```

Use the **arm64-v8a** library. The APK also ships `armeabi-v7a`, whose
addresses differ from every offset this project records.

### 2. Run Il2CppDumper

Use the pinned version, so your output matches the one this project's findings
were derived from:

```text
Il2CppDumper v6.7.46
https://github.com/Perfare/Il2CppDumper
tag v6.7.46, commit 8a521b9c180cf13499253f0818cbc729dca767cb
```

```sh
Il2CppDumper il2cpp-input/libil2cpp.so il2cpp-input/global-metadata.dat il2cpp-output
```

A correct run prints its own confirmation:

```text
Metadata Version: 24
Il2Cpp Version: 24
Generate dummy dll... Done!
```

Check both version numbers read **24**. Anything else means a different library
or a different build was unpacked, and the type trees will not match.

Il2CppDumper is a .NET program whose upstream build targets net7.0. On a machine
with only a newer runtime it will not start; retarget its project file to the
runtime you have and rebuild the unchanged source, rather than looking for a
fault. That is a build-target mismatch, not a bug.

### 3. Pass the directory

The `DummyDll` folder inside the output is what the commands below want. It
holds around 48 assemblies, of which `Assembly-CSharp.dll` carries the game's
own types:

```sh
python3 -m liminal_gate.tester_setup \
  --port 8696 --device emulator-5570 \
  --dummy-dll-dir /path/to/il2cpp-output/DummyDll
```

With it, setup additionally writes `user-data/character-catalog.json` and
`user-data/names.json`, the latter being character, item, and Companion names
decoded from your own metadata for the save editor. Both stay in the ignored
data directory. Without it, setup skips them and says so; everything else works
unchanged.

## Core-story progression

The guided setup uses `--core-story`: it carries only the ordered Chapter 2--42
identities and successor/map-reveal rules. It deliberately accepts each
ordinary stage's nonnegative client-sent stamina and coin fields and does not
bundle a cost/reward table.

For a stricter local installation, derive the reviewed APK's stage metadata
with optional local Unity/IL2CPP parser dependencies and locally derived dummy
assemblies:

If `pip install` reports `externally-managed-environment`, install into a
virtual environment first (`python3 -m venv .venv && source .venv/bin/activate`)
and run the commands below from that activated environment.

```sh
python3 -m pip install '.[master-import]'
liminal-gate-import-battledata \
  --apk local-input/terra-battle-5.5.7-170.apk \
  --dummy-dll-dir /path/to/local/DummyDll \
  --output user-data/derived/battledata-stages.json

liminal-gate-import-story-progression \
  --battledata-stages user-data/derived/battledata-stages.json \
  --output user-data/derived/core-story-progression.json
```

Start the server with
`--story-progression-catalog user-data/derived/core-story-progression.json` to
validate the local APK-derived stage start stamina/coins as well as ordering
and progress. It cannot be combined with `--core-story` or `--story-catalog`.
The derived path uses a client-reported nonnegative Coin result unless a
settlement catalog overrides that stage.

`--story-catalog` instead accepts an operator-authored normalized catalog.
Validate one with:

```sh
liminal-gate-validate-story-catalog --story-catalog /path/to/catalog.json
```

The generic clear path requires the complete client result envelope and is
restart/replay safe. It does not turn this project into a complete historical
reward or drop authority.

## Story outcome and state validation

Use these together when you want stricter generic story settlement:

- `--settlement-catalog` constrains per-stage Coins and item/summon deltas.
- `--story-outcome-catalog` constrains reported items, characters, and
  Companion outcomes.
- `--clear-state-catalog` validates participating character EXP, level, and
  Skill-Boost changes against local rules.

Those catalogs are deliberately operator supplied. They let a self-hosted
instance be strict without bundling a game-data table in this repository.

## Optional local services

The bootstrap server exposes these features only when the corresponding local
catalog is passed at launch:

| Launcher option | Local feature |
| --- | --- |
| `--achievement-catalog` | achievement claim thresholds and rewards (see `--achievements` for the bundled policy) |
| `--message-catalog` | local inbox messages and bounded rewards |
| `--exchange-catalog` | Trading Post offers and exchanges |
| `--statusup-catalog` | status-item use rules |
| `--job-catalog` | ordered job-unlock costs |
| `--rebirth-catalog` | Rebirth recipes and material rules |
| `--summon-skill-catalog` | Battle Summon skill costs |
| `--companion-catalog` | Companion sale/master values |
| `--companion-strengthen-catalog` | Companion EXP and bonus policy |
| `--companion-evolution-catalog` | Companion evolution recipes |
| `--companion-draw-catalog` | local Companion draw pool and costs |
| `--pact-draw-catalog` | ordinary Pact pool, cost, and duplicate policy |

All mutations are designed to persist local state and replay an identical
request safely across restart. Unsupported variants return an explicit error.

The guided setup enables `--pacts`, a built-in local Fellowship/Truth policy.
Use `--pact-draw-catalog` instead when you need a custom Fellowship-only pool;
it cannot be combined with `--pacts`.

### Built-in policies

These carry values recovered from the final client, so the guided setup enables
them without any local catalog. Each is mutually exclusive with the matching
`--*-catalog` option, which still takes precedence for a stricter or custom
local installation.

| Option | What it carries |
| --- | --- |
| `--jobs` | 284 job-unlock rows across 142 characters: Coin and material costs |
| `--rebirth` | all 65 Rebirth recipes, with Joker Lambda as character 1018 |
| `--status-items` | the 7 status-up items and per-character Luck ceilings |
| `--companion-draw` | the 114-Companion rare-slot pool, ticket item, and Energy fallback |
| `--companion-sale` | base Coin values for all 497 Companion masters |
| `--companion-strengthen` | progression values for all 497 masters, plus the same-Companion and ByeBye multipliers |
| `--companion-evolution` | all 153 evolution recipes, including the two duplicate-consuming Metal Minions |
| `--trading-post` | an eight-week rotation of 126 offers, 92 awarding a Companion |
| `--hunting` | Pudding/Tin/Coin Creeps/Puppet stages, costs, and result ceilings |
| `--core-story` | the ordered Chapter 2--42 identities |
| `--pacts` | the local Fellowship/Truth Pact pools and costs |
| `--drop-eligibility` | the login `chrBuddyData` allowlist: 346 character and 497 Companion master IDs |
| `--achievements` | the 8 settleable clear-chapter achievements, each paying 1 Energy and 1x item 50 |

### Why drop eligibility is off by default

Without `chrBuddyData` on login the client sets `canDrop = false` on every
character and Companion and **silently discards every drop it rolls**, so
clears report empty `monsters`/`buddies` no matter what the stage tables say.
`--drop-eligibility` sends the allowlist so rolled drops survive.

It is opt-in because it adds a field to an existing login response. The flag
does not decide *what* drops: per-stage eligibility still governs that through
the enemy record's `DropBuddyID`/`DropBuddyRatio` and the stage's own
`dropBuddies` allowlist and per-battle cap. Marking every recovered master
eligible is a preservation choice, not a recovered per-account entitlement.

`rebirthList` is deliberately omitted from the object. It gates Rebirth
availability rather than drops, and the `availableVersion` values it carries are
not in this repository's bundled Rebirth data, so emitting them would assert a
gate that has not been recovered.

Four of them make an explicit **local policy** choice rather than a claim about
the retired service, and say so in their own code: Companion draw selects
uniformly across its recovered pool instead of asserting the historical
per-rarity base rates, exactly as `--pacts` does; Companion strengthen's
random EXP-bonus weights keep the three documented outcomes reachable without
asserting odds the client never contained; and Hunting's availability
thresholds and Puppet Show item aggregate are preservation policy.

### The Trading Post is the one that is not from the client

Every other built-in policy is recovered from the APK. The Trading Post cannot
be: it was server-fed, so its offers exist nowhere in the client. `--trading-post`
carries the community wiki's permanent-rotation table instead, and every target
and cost name in it resolved cleanly against the client's own master data, which
is why the mapping is trustworthy even though the offers are not.

It rotates. The wiki's eight collapsible sections are the eight weeks of the
cycle, and only one week's offers are browsable or tradable at a time. The
turnover cadence is the original's — every Friday at 00:00 UTC — and stock
restocks on each turn, per account.

What the source does **not** establish is the rotation's phase: which
real-world week was the cycle's first was never recorded. The schedule
therefore anchors to the epoch's own first Friday, which makes it deterministic
and identical on every install without claiming to reproduce any particular
historical week. If you want a different starting week, use
`--exchange-catalog` and declare your own offers.

A traded Companion's level is fixed by neither the client contract nor the
wiki, so these mint at level 1, matching the Companion draw.

## Local event stages and character grants

Event support is deliberately opt-in and operator-local. An event catalog must
contain only stages whose start and clear behavior you have independently
tested with the client. Its character IDs are validated against a matching
catalog derived from your own local APK; neither catalog belongs in Git.

The normal tester command can launch an approved local event catalog once you
also supply your locally generated Il2CppDumper `DummyDll` directory; see
[Generating the `DummyDll` directory](#generating-the-dummydll-directory):

```sh
python3 -m liminal_gate.tester_setup \
  --port 8696 \
  --device emulator-5570 \
  --dummy-dll-dir /path/to/DummyDll \
  --event-catalog /path/to/local-events.json
```

Setup writes the derived `user-data/character-catalog.json`, then starts the
server with both that file and the supplied event catalog. It rejects an event
catalog without `--dummy-dll-dir`, rather than accepting unverified character
IDs. A stage needs its observed chapter, section, entry stamina/Coins, clear
Coins, visibility flag, and character grant IDs; do not add a stage merely
because it appears in a menu.

### The visibility flag is not free-form

The client builds the flag name itself and looks the row up by that exact
string, so a stage's `flag` must be one of only two values:

| Flag | Effect |
| --- | --- |
| `sp_ch_<chapter>` | gates every stage in that chapter |
| `sp_ch_<chapter>-<section>` | gates that one stage |

A stage for chapter 2000, section 1 must therefore use `sp_ch_2000` or
`sp_ch_2000-1`. Anything else is inert — the client never asks about it, so the
stage simply never appears and nothing is logged. The catalog loader now
rejects a mismatched flag with both permitted names in the error, rather than
letting it fail silently at runtime.

`liminal_gate/event_flag_data.py` also lists the other flag families recovered
from the client and from community sources. That list is a reference only, and
is known to be incomplete, so nothing is validated against it.

## Local Hunting stages

Hunting battles run entirely on the client. The server's whole job is to
authorise an entry, charge its cost, and accept a settlement that stays inside
declared bounds, so a stage carries identity, entry cost, unlock policy, and
result ceilings — and no enemy, encounter, reward, or resource data.

The quickest path is the bundled policy, which covers Pudding Time, Tin Parade,
Attack of the Coin Creeps, and Puppet Show at all three zones:

```sh
python3 -m liminal_gate.bootstrap_server \
  --profile profiles/legacy-client-bootstrap.json \
  --state-file user-data/bootstrap-state.json \
  --hunting
```

Stage identities, entry stamina, and the population-derived item ceilings there
are recovered from the final client. Two things in it are explicitly local
policy rather than claims about the original service: availability — each tier
becomes permanent after story chapters 3, 9, and 18, because the retired
rotations were never captured — and Puppet Show's aggregate of 60 items, whose
real-time board has no cumulative spawn counter to recover a true cap from.

**Metal Zone is deliberately absent.** Its results carry EXP and Companion
drops, which this catalog cannot bound, and a settlement carrying Companions is
refused rather than accepted generously.

To declare your own stages instead, supply a catalog. `--hunting` and
`--hunting-catalog` are mutually exclusive, and with neither, Hunting is
unavailable and every Hunting start returns `501`.

```sh
python3 -m liminal_gate.bootstrap_server \
  --profile profiles/legacy-client-bootstrap.json \
  --state-file user-data/bootstrap-state.json \
  --hunting-catalog /path/to/local-hunting.json
```

```json
{
  "schema_version": 1,
  "provenance": "user-supplied",
  "item_slots": 400,
  "max_stack": 99,
  "stages": [
    {
      "family": "pudding",
      "chapter": 1001,
      "section": 1,
      "stamina": 3,
      "coins": 0,
      "entry_item_id": 0,
      "entry_item_count": 0,
      "unlock_chapter": 4,
      "unlock_section": 1,
      "max_coins": 0,
      "max_exp": 0,
      "max_items_total": 5,
      "item_maxima": {"12": 5}
    }
  ]
}
```

`entry_item_id`/`entry_item_count` model a ticket-style entry: declare both or
neither, and the item is consumed on a successful start. `unlock_chapter` and
`unlock_section` are the earliest story point allowed to enter — a local
availability policy, so do not present a schedule as historical behaviour.

The ceilings are the load-bearing part. A settlement is refused with `409`
unless every reported gain fits: coins within `max_coins`, EXP within
`max_exp`, each item within `item_maxima`, and their total within
`max_items_total`. A refusal leaves the wallet,
inventory, roster, and the active stage untouched, so the stage can be retried
honestly. **A visible refusal is the intended outcome for anything unbounded** —
a result carrying Companions or Battle Summons is refused outright, because
those need their own recovered bounds, and a generous success is worse than an
error.

One battle at a time: a Hunting entry is refused while a story or event stage
is active, and vice versa. Progress never moves — a Hunting clear settles
rewards only.

### Selector and fidelity boundary

`get_server_status.constants` now sends the complete client-required constants
block. When a Hunting catalog is enabled, its progress-gated stages populate
`metalHuntingList` and `huntingHuntingList`; without a catalog both lists are
empty. A partial constants object is intentionally never served because the
client indexes required keys directly.

The bundled catalog and any user-supplied catalog remain local preservation
policy. Selector visibility and bounded settlement tests do not prove the
retired service's schedules, rotations, encounter contents, or reward odds.

## Local server configuration file

For a longer-lived setup, keep launcher paths in a TOML file outside the
checkout:

```toml
schema_version = 1
provenance = "user-supplied"
profile = "profiles/bootstrap.json"
state_file = "state/bootstrap-state.json"
event_log = "logs/events.jsonl"
story_progression_catalog = "derived/core-story-progression.json"
story_outcome_catalog = "catalogs/story-outcomes.toml"
clear_state_catalog = "catalogs/clear-state.toml"
```

Run it with:

```sh
liminal-gate-bootstrap-server --config /path/to/user-server/server.toml
```

Relative paths resolve from the TOML file. The configuration is strict and
cannot be mixed with individual launcher flags.

For the complete launcher option list, run:

```sh
liminal-gate-bootstrap-server --help
```

Return to the [README](../README.md) for the supported tester path.
