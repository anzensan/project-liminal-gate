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
- Daily Quests: all fourteen recovered stages, gated once per UTC day.
- Chapter-1100 World Map Special routes, with the client's own native gate.
- Archive Special Quests, the Tower solo adapter, solo Eidolon quests, and all
  eight bundled Strikes Back families.
- Trading Post **weekly rotation**: eight weeks, 126 offers, item and Companion
  targets, turning over every Friday at 00:00 UTC.
- Inbox lifecycle with coin, Energy, item, **character, and Companion** rewards,
  plus the progress-gated retail chapter-ticket presents.
- Hash-validated serving of a user-owned mirrored resource tree.

## Unrecoverable

These are closed questions. Each was decided by the retired server and rendered
by a client that kept no table, so the evidence needed to reproduce them does
not exist anywhere in the APK, the resources, or any surviving capture.

| Behavior | Why it cannot be recovered | What this server does |
| --- | --- | --- |
| Luck Treasure Chest contents | The client holds no reward table at all — the six slots were authored by the server at battle start. 57 preserved launch traces contain no production `luckResult`, and community pool tables state they are incomplete and carry no weights. Pre/post-4.4 rows cannot be safely unioned. | Chest rewards the client reports are accepted only within a stage's recovered ceiling, and refused where no ceiling could be derived. |
| Pact selection odds and duplicate gains | The retired server computed both; the client only displayed the outcome. | Truth selection and duplicate gains follow the community-recorded class bands via the operator's own catalog `rarity`; Fellowship selection is uniform. Labeled local policy. |
| Campaign and event Pact banners | Featured rosters and their rates were live-service state, rotated server-side and never captured. `campaignChrID` and `eventFlag` are refused rather than answered with an invented banner. | Refused explicitly, not silently ignored. |
| Dragon Road, Machine Road, Chapter 1100 payouts | These three declare the absence themselves: empty `dropBuddies`, `allowLucky` 0, and on the Roads `doNotDropExchangeItem` 1. The game states they drop nothing; the Chapter-1100 `dropBuddies` manifests name candidates but no captured clear proves the roll rule. | Coins, items, and Companions are refused. **Experience is paid** — it is the battle's own product and the Roads are species-locked training zones — bounded by a ceiling derived from Metal Zone's own tiers. |
| Trading Post rotation **phase** | Which real-world week was the cycle's first was never recorded. | The eight-week cycle anchors to the epoch's own first Friday: deterministic and reproducible, claiming no particular historical week. |
| Exact story reward and drop settlement | First-clear policy, drop-roll odds, and scripted-stage exceptions were server-side. | Clear coins are a trusted-local client report; Companion, item, and character ceilings come from the operator's own encounter maps, and outcomes above a ceiling are refused. |
| Summon and title inbox rewards | Nothing in the client says where an owned summon or an awarded title is kept, or how either is reported back. | A catalog naming one is refused at load rather than displaying a reward the read cannot deliver. |
| Historical event schedules and live-service families | Never captured. | Story-gated permanent availability, labeled local policy. |

## Open

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
