# Advanced local configuration

This page is for operators tightening or extending the guided core-story path.
The README quick start enables its built-in ordinary Chapter 2--42 progression
policy automatically. Each optional catalog stays local and is supplied by the
operator.

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
| `--achievement-catalog` | achievement claim thresholds and rewards |
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
| `--hunting` | Pudding/Tin/Coin Creeps/Puppet stages, costs, and result ceilings |
| `--core-story` | the ordered Chapter 2--42 identities |
| `--pacts` | the local Fellowship/Truth Pact pools and costs |

Three of them make an explicit **local policy** choice rather than a claim about
the retired service, and say so in their own code: Companion draw selects
uniformly across its recovered pool instead of asserting the historical
per-rarity base rates, exactly as `--pacts` does; Companion strengthen's
random EXP-bonus weights keep the three documented outcomes reachable without
asserting odds the client never contained; and Hunting's availability
thresholds and Puppet Show item aggregate are preservation policy.

### Why there is no built-in Trading Post

The Trading Post is a server-fed system: its offers, prices, stock, and end
dates were sent by the retired service and are not embedded in the client, so
there is nothing recovered to bundle. `--exchange-catalog` therefore stays
operator-supplied, and its contents are your policy rather than a
reconstruction of any historical rotation.

## Local event stages and character grants

Event support is deliberately opt-in and operator-local. An event catalog must
contain only stages whose start and clear behavior you have independently
tested with the client. Its character IDs are validated against a matching
catalog derived from your own local APK; neither catalog belongs in Git.

The normal tester command can launch an approved local event catalog once you
also supply your locally generated Il2CppDumper `DummyDll` directory:

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

### Not yet available

The client's Hunting **selector** is not populated. It reads
`get_server_status.constants`, which this server does not send at all, and
`docs/server-protocol.md` records that a partial `constants` object crashes the
client because its setter directly indexes the first 31 keys. Until that
projection is captured and proved against the real client, these stages are
reachable by a client that already knows the identity, not by browsing the
menu. Metal and Puppet families additionally need their EXP, Companion, and
timed-result bounds recovered before they can be declared.

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
