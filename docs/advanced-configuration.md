# Advanced local configuration

This page is for operators extending the basic Chapter 2-1 tester path. None
of these inputs are required for the README quick start. Each catalog stays
local and is supplied by the operator.

## Core-story progression

With optional local Unity/IL2CPP parser dependencies and locally derived dummy
assemblies, extract the reviewed APK's stage metadata:

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
use the locally derived ordered Chapter 2--42 sequence. It cannot be combined
with `--story-catalog`. The derived path validates ordering/progress and uses a
client-reported nonnegative Coin result unless a settlement catalog overrides
that stage.

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
