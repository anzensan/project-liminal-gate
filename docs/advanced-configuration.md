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

### Composing a story-outcome catalog from your own recovered drops

`--story-outcome-catalog` is the option that decides whether a story clear can
mint a Companion. Without one the server writes no `buddyInfo` at all, so a
self-hosted instance can play the entire story and never see a Companion drop
even though the client rolled one. Authoring the catalog by hand means writing a
per-stage Companion ceiling for every ordinary stage, which is why it can be
composed instead.

**Read the limits below before using it.** This is opt-in strictness, not a
strictly better setting.

#### 1. Extract the native encounter map

This is the one import in the project that a Unity type-tree reader cannot
serve. The chapter battle scripts are compiled into the native library rather
than stored as serialized data, so recovering which enemies a stage spawns needs
a disassembler. Alongside your APK you need two things:

- the `dump.cs` file from the **same** Il2CppDumper run that produced your
  `DummyDll` directory -- it is that directory's sibling in the Il2CppDumper
  output, and it supplies the method names, managed virtual slot numbers, and
  the `Enemies` enum that the disassembly alone does not carry;
- an `objdump` that can disassemble AArch64 (system binutils or LLVM both work).

```sh
python3 -m liminal_gate.native_encounter_importer \
  --apk local-input/terra-battle-5.5.7-170.apk \
  --dump-cs /path/to/il2cpp-output/dump.cs \
  --output user-data/derived/native-encounters.json
```

It reports how many stages resolved every spawn and how many rest on an inferred
variant. **ARM64 only.** The APK also ships `armeabi-v7a`, whose class header and
vtable stride differ; the two ABIs are compiled from one program, so reading the
32-bit library would add a second instruction decoder for no additional
information. Every offset in this project's documentation refers to arm64.

#### 2. Compose the catalog

```sh
python3 -m liminal_gate.story_outcome_generator \
  --apk local-input/terra-battle-5.5.7-170.apk \
  --dummy-dll-dir /path/to/il2cpp-output/DummyDll \
  --native-encounters user-data/derived/native-encounters.json \
  --character-catalog user-data/character-catalog.json \
  --output user-data/derived/story-outcomes.json
```

The generator hashes the selected APK and requires both the native encounter
map and character catalog to name that exact APK. Cross-build inputs fail
instead of being joined. Generated JSON retains the APK, native encounter,
character catalog, optional baseline, `dump.cs`, and `libil2cpp.so` hashes plus
the native vtable-calibration label. An `unverified` calibration remains
allowed for a different client build, but is reported and preserved rather
than silently presented as verified.

Two sources are unioned, and the larger ceiling wins:

- each stage's own `BattleData.Section.dropBuddies` allowlist, which packs a
  Companion and its per-clear cap into one integer;
- the native encounter map joined to `EnemyData`, where a stage's ceiling for a
  Companion is how many enemies able to drop it that stage spawns.

Neither subsumes the other. The allowlist covers stages the native map cannot
resolve; the native map covers Companions the allowlist omits.

#### Item and character ceilings

`StoryOutcomeRule` also carries `item_maxima` and `character_maxima`, and an
empty ceiling **forbids** the outcome rather than permitting it. Both are
therefore derived from the same per-enemy records the Companion ceiling reads,
so a clear that legitimately rewards an item or a recruited monster is accepted:

- **Items** come from `EnemyParams.items`, a four-slot `ItemCode` array where
  `code >> 8` is the item and `code & 0xFF` the count. 845 recovered enemy
  records carry at least one. There is no per-item ratio, so every item an enemy
  names contributes a ceiling.
- **Characters** come from `EnemyParams.DropJobID`, which names a `ChrJobParams`
  row whose `chrID` is the character the client recruits. A zero `DropRatio`
  never rolls and contributes nothing, matching the Companion reading.

A stage the native map cannot join has no item or character evidence and its
ceilings stay empty. The run report counts those stages, so you can see exactly
where a clear reporting an item or a recruited monster would be refused. Pass an
operator-authored catalog as `--baseline` to fill them: its capacities, maxima,
and Companion drop levels are carried through unchanged and the recovered
ceilings are unioned on top.

**This catalog is optional strictness.** The guided setup does not pass it, and
without it the server does not constrain reported outcomes at all -- items and
monster drops settle from the client's own battle result. Supply it only when
you want the stricter validation and accept its coverage limits.

Three further boundaries, all reported by the commands themselves:

- **Chapters 38--42 cannot be joined at all.** The client shipped those
  chapters' battle scripts without their `EnemyData` rows -- 52 symbols with no
  record anywhere in the APK. Those stages keep only their own `dropBuddies`
  allowlist. This is permanent and is not a fault in the import.
- **Chapters 1--7 are not in the native map.** Their encounters live in the
  scenario scripts rather than in compiled chapter classes, so they also keep
  only their `dropBuddies` allowlist.
- **Variant initializers are inferred, not confirmed.** A spawn may name a base
  enemy with a behavioural modifier applied; it resolves to the base enemy's
  record and is marked `exact: false` in the encounter import, and the summary
  counts the stages whose ceiling depends on one. Pass `--exact-only` to drop
  those contributions.

A dropped Companion is minted at level 1, following the one recovered drop
manifest that states a level -- Metal Zone's two Companions. A `--baseline`
entry overrides it per Companion.

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
| `--summon-skill-catalog` | Battle Summon skill costs (see `--summon-skills` for the bundled policy) |
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

### Composing an event catalog

The archived events sit in BattleData beside the main story, so their entry
stamina and start costs come out of the same import that serves ordinary
stages -- nothing here needs native disassembly:

```sh
python3 -m liminal_gate.event_catalog_generator \
    --battledata user-data/battledata.json \
    --character-catalog user-data/character-catalog.json \
    --output user-data/event-catalog.json
```

The generator contributes the 13 recovered manifest identities -- selector flag,
chapter, and character association -- and takes everything else from your own
files. Character grants are still validated against your character catalog and
are omitted with a note when a character is missing, which is the boundary
`--event-catalog` exists to keep.

Two things it does not claim. The release order is local archive policy: the
original schedule was never recovered, so the events are permanently available
rather than scheduled. And an event clear credits no Coins, because BattleData
records a start cost for these sections but no clear reward -- the same reading
that leaves Dragon and Machine Road settling at zero.

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
| `--summon-skills` | all 44 Battle Summon skill tiers across the 16 Summons, with their material costs |

### Choosing which saved account to play

An account is keyed by the client's device UUID, so clearing app data or
reinstalling signs the client into a new, empty account while the previous save
stays in the file. Guided setup lists what it finds before launching and, when
another played account has more progress than the active one, offers to switch:

```
Another saved account has more progress than the one the client is on.
  1) 4f2c...  unlocked chapter 6-1
  0) keep the current account
```

Outside guided setup the same choice is one command, with the server stopped:

```sh
python3 -m liminal_gate.account_state inspect user-data/bootstrap-state.json
python3 -m liminal_gate.account_state switch user-data/bootstrap-state.json \
    --account <accountId> --yes
```

`switch` **exchanges** the chosen save with the active one, so nothing is
destroyed and switching back is the same command with the other ID. A
timestamped `.pre-switch` copy is written first. Same-second operations receive
distinct suffixes and use exclusive file creation, so an earlier safety copy is
never overwritten.

That is the difference between it and `adopt`, which moves a save onto another
UUID and discards whatever was there. Use `adopt` to recover a save onto a
reinstalled client permanently; use `switch` to choose between saves you intend
to keep.

### If the game crashes at the title screen on a high-memory device

A Unity 2017 IL2CPP build can fault on modern phones with a lot of RAM. The
symptom is the app closing itself a few seconds after launch, and the device log
shows Unity's own message just before a `signal 11 (Segmentation fault)`:

```
E Unity : Using memoryadresses from more that 16GB of memory
```

The game is not mis-signed or mis-patched when this happens; its 64-bit process
is simply being handed an address the 2017 runtime cannot represent.

A 32-bit process has a 4 GB address space and never produces one, and the APK
ships both ABIs, so dropping the 64-bit tree sidesteps it:

```sh
python3 -m liminal_gate.apk_patcher \
    --source-apk <your.apk> --patch-plan <plan.json> \
    --output-apk patched.apk --drop-abi arm64-v8a
```

Nothing is lost by doing this. The server address lives in the ABI-independent
metadata, and the other local edits are applied to both libraries, so the 32-bit
build keeps every one of them. The archive is about 20 MB smaller. Align and
sign the result as usual.

The patcher refuses to drop an ABI the archive does not carry, and refuses to
drop them all.

### Drop rates: no campaign doubling, deliberately

The client's drop roll multiplies its recovered per-enemy percentage by a daily
bonus when one is active: `DailyBonusType.ItemDropUp` doubles the item ratio and
`MonsterDropUp` doubles the monster-recruit ratio. Companion and Battle Summon
drops are never doubled.

Whether a bonus is active is read from `EventManager.GetBoolean("enableDailyBonus")`,
which is false for an absent key, a wrong type, or an event outside its date
window. **This server delivers no such event parameter, so no doubling ever
fires and the recovered base percentages are exact.**

That is a deliberate default, not an oversight. The original schedule ran a
bonus two days in three for one chapter in five, anchored to a server-corrected
clock, and none of that is reproducible here. Serving a constant base rate is
the honest choice.

It is written down because it is fragile: anything that starts delivering event
parameters under that name would silently double item and monster drop rates
across the whole game. If you add event-parameter delivery, decide about
`enableDailyBonus` explicitly rather than inheriting it.

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

The object carries all three of `chrList`, `buddyList`, and `rebirthList`. That
is not optional: the client null-guards `chrBuddyData` itself and then reads its
child lists unconditionally, so sending the object with a list missing throws
inside its login reader and the client hangs on "Connecting..." forever. An
earlier build omitted `rebirthList` on the reasoning that it gates Rebirth
rather than drops -- true, and irrelevant.

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

## The Chapter-1100 world map routes

Two extra points appear on the ordinary world map once the story has cleared
Chapter 34: Shin'en Lambda and Mutoh Lambda, five one-battle stages each. There
is no flag for them and no catalog to supply. The client draws both points
itself from `UIMap.InitPoints0`, so the server simply accepts their entries.

Each entry costs the recovered 25 stamina and no Coins, and a route's battles
open one at a time; clearing a battle you have already cleared is allowed and
does not move the frontier backwards. A clear never touches core story progress:
a request that tries to advance `progressCode` from one of these stages is
refused, because this is a World-0 special that must not overwrite the ordinary
story's own field.

Settlement is empty on purpose. The embedded `dropBuddies` manifest proves which
Companions each stage could yield — for example a single candidate on each
route's opening battle, three on its fourth — but nothing captured proves whether
candidates are guaranteed, exclusive, or independently rolled. Rather than
invent a rule, the server refuses any reported Companion, Coin, EXP, item,
monster, Summon, or Luck result here and keeps the manifest for comparison
against a future trace. Continue is likewise unavailable during these battles,
matching the chapter's own notice that it cannot be continued after a game over.

One caveat worth recording: the play order within a route is inferred, not
confirmed. The client stores the ten stages under section ordinals whose titles
run "battle 4, 3, 2, 1, 5", and this server follows the battle numbering in the
titles rather than the ordinals. The reason is that the section titled "battle
1" is, in each route independently, the only one of its five assumed at level 80
instead of 90 — an ordinal ordering would put the easiest fight last.

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
