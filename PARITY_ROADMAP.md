# Public parity roadmap

Project Liminal Gate is not yet feature-parity with the private preservation
reference. This roadmap records the remaining source-only work without
publishing original data, captures, account state, or generated catalogs.

## Runnable now

- Local bootstrap, account state, tutorial, and verified Chapter 1/2 flow.
- Built-in ordinary Chapter 2--42 story start/clear/map-reveal progression;
  optional locally derived catalogs can additionally validate start values.
- Built-in local Fellowship/Truth Pact draws with durable result replay.
- Local APK routing/guarded patch/sign workflow.
- Built-in local job unlock, Rebirth, status-up item, full Companion (draw,
  sale, strengthen, evolution), and Trading Post policies; Battle Summon skill
  progression stays catalog-gated.
- Built-in local Hunting stages for Pudding Time, Tin Parade, Attack of the
  Coin Creeps, and Puppet Show, with charged entry and bounded settlement.
- Built-in local Metal Zone with its ticket-or-stamina entry and bounded EXP and
  Companion settlement, the two Roads, and the `get_server_status.constants`
  block the client's Huntland selectors and enable gate require.
- Built-in local Chapter-1100 World Map Special routes (Shin'en and Mutoh), with
  charged entry, per-route progression, and a zero-reward settlement.
- Guided Archive Special Quests for recovered Chapters 2000, 2001, 2002, 2004,
  and 2006, derived from the tester's own BattleData and character catalog,
  plus all eight bundled Strikes Back families.
- Hash-validated serving of a user-owned mirrored resource tree.

## Required for broad single-player parity

| Family | Required user-local input/state | Current boundary |
| --- | --- | --- |
| Story rewards and drops | Character, item, summon, encounter, and reward catalogs | Bulk ordinary Chapter 2--42 order/progress/map reveal is available. **Reported outcome ceilings are composable:** a native encounter importer reads the compiled chapter battle programs out of the user's own ARM64 `libil2cpp.so` (with their Il2CppDumper `dump.cs`), and a generator joins those spawns to per-enemy Companion, item, and recruitable-character records, then unions the result with each stage's `BattleData` Companion allowlist. ARM64 only; armeabi-v7a is follow-up. A fully joined native stage can therefore carry Companion, item, and character ceilings. Stages the native map cannot join keep empty item/character ceilings and refuse those outcomes: Chapters 1--7 use scenario-script encounters, while Chapters 38--42 include 52 symbols for which the client shipped no `EnemyData` row. Variant initializers resolve to a base enemy and stay marked inferred. The generated catalog rejects native/character inputs from a different APK and retains their hashes and calibration status. Clear coins remain a trusted-local client report; exact item/summon settlement, first-clear policy, drop-roll odds, and scripted-stage exceptions remain incomplete. |
| Tavern and Companions | Nothing for normal pulls, draws, or sales; equipment rules remain | Built-in local Fellowship/Truth Pacts, the 114-Companion rare-slot draw pool, and base sale values for all 497 masters. Selection is uniform local policy, not historic odds. Fate/ticket/campaign/event variants, party selection, and equipment lifecycle remain incomplete. Strengthening and evolution are now built in. |
| Battle Summons | Summon acquisition, ownership, party selection, and any remaining skill tiers | Skill unlock now ships as a built-in policy carrying all 44 recovered tiers; acquisition and authoritative lifecycle remain absent. |
| Optional/event stages | Named stage manifests, rewards, schedules where applicable | Guided setup now composes an event catalog from the user's own BattleData and character catalog plus the 13 recovered manifest identities. The five Archive families enter the normal Special selector; bundled Counter Descent remains authoritative for the eight Strikes Back identities. The permanent unlock cadence, zero clear Coins, and first-section associated-character grants are labeled local policy. Reward tables beyond section economics remain unrecovered, and original-client archive/Strikes Back clears are pending. An earlier revision of this row claimed a permanent evidence gap here, on the finding that only 184 of the event/special symbols in the client's `Enemies` enum carried an `EnemyData` record. **That was wrong and is retracted.** It came from reading an `Enemies` value as a record's `ID` field; the value is an ordinal into `EnemyData`, so value V is index V - 1, and the record's own `ID` is a banded internal number that only coincides with the value below 993. Every one of the 1930 real enum symbols has a record. A secondary source could still only be bundled if it cross-validated completely against client master data, the way the Trading Post did. |
| Hunting | Nothing; every bundled family is self-contained | Pudding/Tin/Coin Creeps/Puppet and Metal Zone are declared with recovered identities, entry stamina, the Item 50 ticket contract, and population-derived ceilings. The client's selectors are now populated: `get_server_status.constants` supplies both zone lists plus the `currentVersion_*` pair its top-level enable gate reads. Labeled local policy: every availability threshold, Puppet's aggregate, and Metal's per-zone EXP ceilings. Dragon and Machine Road settle at zero because BattleData gives them no rewards. A clear's submitted character levels are still a trusted-local client report, which matters most here because Metal is the EXP family. |
| World Map Special (Chapter 1100) | Nothing; the ten stages are self-contained | Both five-battle routes are declared with their recovered identities, the 25-stamina entry, and their `dropBuddies` Companion candidate manifests. The entry gate is the native one: `UIMap.InitPoints0` draws both map points after normal Chapter 34, so no threshold was chosen here. Play order within a route is Strongly inferred, not Confirmed — section ordinals run 4, 3, 2, 1, 5, and the battle numbering in the titles is preferred because the section titled "battle 1" is, in both routes independently, the only one of five assumed at level 80 rather than 90. Settlement is deliberately zero: the manifests prove *which* Companions a stage could yield but no captured clear proves the roll rule, so a reported Companion is refused rather than minted from a guess. |
| Trading Post | Nothing for the bundled rotation; a schedule remains unrecovered | Nested browse, item **and Companion** offers, and bounded settlement are available. The offers are wiki-sourced rather than client-recovered, because the Trading Post was server-fed; every name in them resolves against client master data. One rotation snapshot, not a schedule. Untrusted count credit remains absent. |
| Messages/achievements | Nothing for the retail chapter-ticket presents; local catalogs remain optional | Progress-gated Chapter 5/7 Metal Ticket and Chapter 6/8/10 Companion Ticket inbox presents, catalog-gated clear-chapter claims, and local inbox render/read/delete are available. Campaign delivery, Luck Chest ticket payouts, and unsupported reward kinds remain absent. |
| Differential certification | Excluded private-reference fixtures and user-local generated profiles | Required before any parity claim. |

## Deliberately outside local single-player parity

PvP, matchmaking, social/friend services, active commerce, advertising, and
hosted live-service functions remain disabled. This project does not host an
official service, provide payment access, or distribute client/content files.

## Publication condition

Adding a family requires a new provenance review, user-input boundary,
atomic/replay-safe state design, clean-checkout HTTP proof, and a private legal
rationale. Passing those gates establishes only the documented local behavior,
not authorization or historical-service fidelity.
