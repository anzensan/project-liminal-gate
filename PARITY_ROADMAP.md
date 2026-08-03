# Public parity roadmap

What this server does, what it will never do, and why. The distinction that
matters is not "done or not done" but **why** something is missing: work still
to do, or evidence that no longer exists.

Three categories are used below and they are not interchangeable:

- **Implemented** — the behavior runs, with real-HTTP and restart coverage.
- **Unrecoverable** — the retired service computed it, the client only rendered
  it, and no capture survives. No amount of further work recovers these. They
  are settled as explicitly labeled local policy, or refused outright.
- **Open** — genuinely remaining work.

## Implemented

- Local bootstrap, account state, tutorial, and verified Chapter 1/2 flow.
- Ordinary Chapter 2--42 story start/clear/map-reveal progression, with
  optional locally derived catalogs validating start values.
- Fellowship and Truth Pact draws with durable result replay, the Fate (`luckType`)
  variant, and the permanent Item 81 ticket draw.
- Companion draw, sale, strengthen, evolution, and the full equipment
  lifecycle: equip, unequip, retarget between characters, and party selection,
  authorized against character-family and active-job species rules derived from
  the operator's own APK.
- Local APK routing, guarded patch, and signing workflow.
- Job unlock, Rebirth, status-up items, Trading Post, and Battle Summon skill
  progression (all 44 recovered tiers).
- Hunting: Pudding Time, Tin Parade, Attack of the Coin Creeps, Puppet Show,
  Metal Zone with ticket-or-stamina entry, Money Money Time, Crystal Road, and
  the two Roads, with the `get_server_status.constants` block the client's
  Huntland selectors and enable gate require.
- Daily Quests: all fourteen recovered stages, gated once per UTC day, with
  the rotation the login response names and per-slot play times. Both Yamamoto
  Puzzle Quests settle the one Companion their own `dropBuddies` manifest
  names, at level 1; they are the only two of the fourteen that carry one.
- The final client's native 15-day ordinary-story bonus rotation: item drops
  x2, monster recruits x2, then no bonus, rotating through five chapter groups.
  Guided core story supplies only the recovered boolean gate; the client owns
  the date, chapter selection, badge, and multiplier.
- The two secondary world maps: BreaSoul's twenty sections and the ten Five
  Emperors descents, each behind the client's own map predicate.
- Luck: the stat grows from play, and Luck Treasure Chests are authored at
  battle start for the thirty story stages the record documents.
- Chapter-1100 World Map Special routes, with the client's own native gate.
- Archive Special Quests, the Tower solo adapter, solo Eidolon quests, and all
  eight bundled Strikes Back families.
- Trading Post **weekly rotation**: eight weeks, 126 offers, item and Companion
  targets, turning over every Friday at 00:00 UTC.
- Inbox lifecycle with coin, Energy, item, **character, and Companion** rewards,
  plus the standard daily login schedule. Progress-gated retail chapter tickets
  settle directly as compatibility policy after Issue 33 disproved milestone
  mail acceptance in the final client.
- Hash-validated serving of a user-owned mirrored resource tree.

## Unrecoverable

These are closed questions. Each was decided by the retired server and rendered
by a client that kept no table, so the evidence needed to reproduce them does
not exist anywhere in the APK, the resources, or any surviving capture.

| Behavior | Why it cannot be recovered | What this server does |
| --- | --- | --- |
| Luck Treasure Chest **rates and pool weights** | The client holds no reward table and no spawn rule — `Character.get_luckRate` is a tenths-to-display multiply and nothing more — so the server authored all six slots at battle start. No capture survives, and the community pool tables state they are incomplete and carry no weights. What *is* published is the endpoints: Mistwalker's Ver 4.2.0 post gives the class caps and the eight-stamina gate, and the record gives four probability anchors. | **Implemented**, since the endpoints are sourced even though the curve is not. Chests are authored at start for the thirty story stages the record documents; every other stage yields six empty slots rather than an invented reward. Tier odds interpolate between the published anchors with no free parameter. Exactly two numbers are chosen: the per-stamina Luck gain chance, and equal-weight selection within a tier. |
| Pact selection odds and duplicate gains | The retired server computed both; the client only displayed the outcome. | Truth selection and duplicate gains follow the community-recorded class bands via the operator's own catalog `rarity`; Fellowship selection is uniform. Labeled local policy. |
| Campaign and event Pact banners | Featured rosters and their rates were live-service state, rotated server-side and never captured. `campaignChrID` and `eventFlag` are refused rather than answered with an invented banner. | Refused explicitly, not silently ignored. |
| Dragon Road, Machine Road, Chapter 1100 payouts | These three declare part of the absence themselves: empty `dropBuddies`, and on the Roads `doNotDropExchangeItem` 1. The Luck chest was also read off `allowLucky` 0; that reading is withdrawn, because every story chapter sets that flag while still producing chests (see `docs/findings.md`, 2026-08-02). Dragon Road's chest stays refused because the community record's own no-chest list names it; Machine Road's and Chapter 1100's are undetermined and refused as local policy. The Chapter-1100 `dropBuddies` manifests name candidates but no captured clear proves the roll rule. | Coins, items, and Companions are refused. **Experience is paid** — it is the battle's own product and the Roads are species-locked training zones — bounded by a ceiling derived from Metal Zone's own tiers. |
| Trading Post rotation **phase** | Which real-world week was the cycle's first was never recorded. | The eight-week cycle anchors to the epoch's own first Friday: deterministic and reproducible, claiming no particular historical week. |
| Exact story reward and drop settlement | First-clear policy, drop-roll odds, and scripted-stage exceptions were server-side. | Clear coins are a trusted-local client report; Companion, item, and character ceilings come from the operator's own encounter maps, and outcomes above a ceiling are refused. |
| Summon and title inbox rewards | Nothing in the client says where an owned summon or an awarded title is kept, or how either is reported back. | A catalog naming one is refused at load rather than displaying a reward the read cannot deliver. |
| Historical event schedules and live-service families | Never captured. | Story-gated permanent availability, labeled local policy. |

## Open

- The separately branded seven-day newcomer login event needs an item and
  Companion identity audit before it can be added beside the standard login
  schedule. It is not silently approximated from reward names.
- **Original-client verification beyond Chapter 9.** The client is played
  through Chapter 9 on physical hardware; Chapter 2-1 is the deepest point
  backed by preserved request traces. Extending both is open work.
- Chapters 1--7 and 38--42 keep empty item/character ceilings: the first use
  scenario-script encounters rather than compiled battle programs, the second
  include 52 symbols for which the client shipped no `EnemyData` row. Those
  outcomes are refused rather than guessed.
- armeabi-v7a native encounter import; ARM64 is implemented.
- Differential certification against excluded private reference evidence.

## Deliberately outside local single-player parity

PvP, matchmaking, social and friend services, active commerce, advertising,
campaign delivery, and hosted live-service functions remain disabled. This
project does not host an official service, provide payment access, or
distribute client or content files.

## Publication condition

Adding a family requires a new provenance review, user-input boundary,
atomic/replay-safe state design, clean-checkout HTTP proof, and a private legal
rationale. Passing those gates establishes only the documented local behavior,
not authorization or historical-service fidelity.
