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
- Hash-validated serving of a user-owned mirrored resource tree.

## Required for broad single-player parity

| Family | Required user-local input/state | Current boundary |
| --- | --- | --- |
| Story rewards and drops | Character, item, summon, encounter, and reward catalogs | Bulk ordinary Chapter 2--42 order/progress/map reveal is available. **Reported outcome ceilings are composable:** a native encounter importer reads the compiled chapter battle programs out of the user's own ARM64 `libil2cpp.so` (with their Il2CppDumper `dump.cs`), and a generator joins those spawns to per-enemy Companion, item, and recruitable-character records, then unions the result with each stage's `BattleData` Companion allowlist. ARM64 only; armeabi-v7a is follow-up. A fully joined native stage can therefore carry Companion, item, and character ceilings. Stages the native map cannot join keep empty item/character ceilings and refuse those outcomes: Chapters 1--7 use scenario-script encounters, while Chapters 38--42 include 52 symbols for which the client shipped no `EnemyData` row. Variant initializers resolve to a base enemy and stay marked inferred. The generated catalog rejects native/character inputs from a different APK and retains their hashes and calibration status. Clear coins remain a trusted-local client report; exact item/summon settlement, first-clear policy, drop-roll odds, and scripted-stage exceptions remain incomplete. |
| Tavern and Companions | Nothing for normal pulls, draws, or sales; equipment rules remain | Built-in local Fellowship/Truth Pacts, the 114-Companion rare-slot draw pool, and base sale values for all 497 masters. Selection is uniform local policy, not historic odds. Fate/ticket/campaign/event variants, party selection, and equipment lifecycle remain incomplete. Strengthening and evolution are now built in. |
| Battle Summons | Summon acquisition, ownership, party selection, and any remaining skill tiers | Skill unlock now ships as a built-in policy carrying all 44 recovered tiers; acquisition and authoritative lifecycle remain absent. |
| Optional/event stages | Named stage manifests, rewards, schedules where applicable | A public generator composes an event catalog from the user's own BattleData import plus the 13 recovered manifest identities; release order and zero clear Coins are labeled local policy. Reward tables beyond the section economics remain unrecovered, and are a permanent evidence gap rather than pending work: of 798 event/special enemy symbols in the client's `Enemies` enum, only 184 carry an `EnemyData` record at all, so for most events the enemies themselves were server-side. A secondary source could only be bundled if it cross-validated completely against client master data, the way the Trading Post did. |
| Hunting | Nothing; every bundled family is self-contained | Pudding/Tin/Coin Creeps/Puppet and Metal Zone are declared with recovered identities, entry stamina, the Item 50 ticket contract, and population-derived ceilings. The client's selectors are now populated: `get_server_status.constants` supplies both zone lists plus the `currentVersion_*` pair its top-level enable gate reads. Labeled local policy: every availability threshold, Puppet's aggregate, and Metal's per-zone EXP ceilings. Dragon and Machine Road settle at zero because BattleData gives them no rewards. A clear's submitted character levels are still a trusted-local client report, which matters most here because Metal is the EXP family. |
| Trading Post | Nothing for the bundled rotation; a schedule remains unrecovered | Nested browse, item **and Companion** offers, and bounded settlement are available. The offers are wiki-sourced rather than client-recovered, because the Trading Post was server-fed; every name in them resolves against client master data. One rotation snapshot, not a schedule. Untrusted count credit remains absent. |
| Messages/achievements | Local message and achievement policy/catalogs | Catalog-gated clear-chapter claims and local inbox render/read/delete lifecycle are available; campaign delivery and unsupported reward kinds remain absent. |
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
