# What works right now

This is the detail behind the summary in the [README](../README.md). It
describes what the guided setup enables, what stays locked, and why. None of it
is needed to install; read it when you want to know what to expect from a
running game, or when a screen is empty and you want to know whether that is a
fault.

## The evidence checkpoint

The verified original-client path reaches and clears **Chapter 9**, played
continuously on a physical device without a client-visible failure. The guided
setup also enables a bulk ordinary-story policy through Chapter 42; that is not
a claim that every later reward, drop, or scripted scene has been historically
reproduced.

The deepest point backed by preserved request traces rather than by playing
remains Chapter 2-1. Both matter: the trace checkpoint is what proves the wire
shapes exactly, and the playthrough is what proves the game is actually
finishable.

This remains a tester build. Later story stages may still need individual
compatibility fixes despite the successful physical-device playthrough.

## Story and Pacts

Quest entry costs no stamina. The bar the client draws reads full and never
falls, so nothing gates how many stages you can play in a sitting, and the
in-game stamina refill answers "no need to refill" rather than taking an Energy.
The recovered meter is intact and unchanged behind `--enable-stamina`; see
[The stamina meter is off by default](advanced-configuration.md#the-stamina-meter-is-off-by-default)
for why it ships off and how to charge it.

The guided setup enables ordinary story progression beyond the tutorial, through
Chapter 42, and local ordinary Pacts:

- **Pact of Fellowship** (`kind=0`) spends 3,000 Coins per pull.
- **Pact of Truth** (`kind=1`) spends 5 Energy per pull, 50 for ten. New local
  accounts receive 50 free Energy, which is exactly one ten-pull.
- **Pact of Fate** uses those same two costs and corresponding local pools when
  the client sends `luckType=true`; its duplicates gain one local-policy level
  and 5.0 Luck instead of Skill Boost.

The client may submit any affordable batch from 1 through 10 even though its
controls normally label 1, 5, and 10. The included pools are bounded local
policy, not a claim about the retired service's membership.

**Rates and duplicate gains are class-based.** A recruited duplicate raises an
existing character by 6 levels and 12.0% Skill Boost at Z, 5 levels and 10.0% at
SS and S, and 1 level and 5.0% at A and below. Pact of Truth selection is
weighted 4% Z, 10% SS, 15% S, and 71% split evenly across A and B. The class of
each pooled character is read from the `rarity` field of your own
APK-derived character catalog, so nothing about your roster is bundled here.

Those two tables are **local preservation policy taken from the community
record, and they cannot be upgraded to recovered values.** The final client
never computed either one: it renders whatever the server sent, through
`UIPactResult.PrepareShow(chrId, addedLevels, addedSkillBoost, addedLuck)`, and
carries no rate table of its own. They replace an earlier flat default of +1
level and +1.0% for every class, which matched no source at all. Pact of
Fellowship keeps uniform selection because no comparable record of its rates was
found. If you have a better-sourced table, `--pact-draw-catalog` replaces the
bundled one.

The `kind=20` form spends one Item 81 Fellowship Ticket per result before
Coins, for either an ordinary Fellowship draw or its `luckType=true` Fate
variant, in batches of one through ten exactly as the Coin and Energy forms
allow. The same ticket pays for the Coin-priced Companion pull on the
Companion page (`do_buddy_slot`), which draws the 81 normal-slot Companions.
Mixed ticket/coin batches, campaign Pacts, and event-specific Pacts remain
unsupported.

Ordinary clear results use the client-reported local result; the server does
**not** bundle an original reward/drop table. Unusual scripted stages may still
stop with a Network Error until they are given a specific compatibility rule.

### Testing the starter Energy grant

The 50-Energy grant applies when a local account is first created. To test it
after upgrading an existing setup, use a new local data directory and clear only
this test app's data before choosing **New Game** again:

```sh
python3 -m liminal_gate.tester_setup --data-dir user-data/pact-test --port 8696 --device emulator-5570
```

Then use the reset commands in [Play](../README.md#6-play) with your own serial
and package name. This preserves your earlier `user-data/` test state.

## Optional areas open on story progress, so most are locked at first

Hunting, Metal Zone, Special Quest, Tower, and world-map cards stay unavailable
until your account has finished the chapter each row waits for.

| Area | Available after clearing |
| --- | --- |
| Hunting tier 1 — Pudding Time, Tin Parade, Coin Creeps, Puppet Show | Chapter 3 |
| Hunting tier 2 | Chapter 9 |
| Hunting tier 3 | Chapter 18 |
| Metal Zone 1, Dragon Road, Machine Road | Chapter 3 |
| Crystal Road | Chapter 3 |
| Metal Zones 2 to 7 | Chapters 8, 12, 17, 21, 26, 30 |
| Bahamut Descent | Chapter 2 |
| Jade Dragon Hunt | Chapter 4 |
| Leviathan Descent | Chapter 10 |
| Lucia archive | Chapter 13 |
| Odin Descent | Chapter 20 |
| Strikes Back families | Chapters 5 through 18, one family per chapter |
| Tower of Temptation 9010-1 | Chapter 3 |
| Melting Pot: Lizardfolk, Beastfolk, Human (9100 to 9102) | Chapter 3 |
| Cryptid Forest (world map) | Chapter 5 |
| Orbling Cavern (world map) | Chapter 6 |
| Shin'en Lambda and Mutoh Lambda (world map) | Chapter 34 |

Those thresholds are local preservation policy, not recovered schedules. The
retired event and Hunting rotations were not captured, so the standard setup
makes each row permanent after its story gate. **Empty optional screens on a new
account are expected, not a fault.**

The three world-map rows are the exception: their chapters are the client's own
gate rather than a policy this project chose. Cryptid Forest and Orbling Cavern
each draw their own permanent map point on World 1 and open a two-card selector
the client fills from its own list, so the server opens the door and nothing
more. Cryptid Forest farms Dracorin's job materials and carries the Lucky
Runner that raises party Luck; Orbling Cavern awards Bahl OIII and Grace OIII,
one per card, and the drop stops once you hold the Companion.

The Chapter 34 pair are the client's own gate too, and their five battles each
open one at a time.

### The Roads give EXP plus one documented channel each

**Each Road admits one species, and only that species.** Dragon Road takes
Dragons and Machine Road takes Machines: they are the only two sections in the
game that declare a species lock at all, and one party member outside it is
enough to be turned away at the start, with the client's own refusal. The limit
went unasserted until 2026-08-08, which is why either Road could be used as a
general-purpose EXP route before then.

**Dragon Road and Machine Road pay experience** — no Coins, no Companion
drops, no Luck chest. The Companion refusal is the game's own: each section
declares an empty Companion drop list in your copy of its data. The Luck chest
refusal used to rest on those sections setting `allowLucky` to 0, and no longer
does — every story chapter sets that flag while still producing chests, so it
does not mean "no chest". Dragon Road stays refused because the community
record's own no-chest list names it; Machine Road is undetermined and refused
as local policy.

Each Road also settles the one reward its contemporaneous community record
documents, bounded rather than reproduced. Machine Road accepts up to a
generous ceiling of the four Star items — its `doNotDropExchangeItem` flag
governs exchange items by name, and reading it as "no items ever" would risk
refusing a won battle. Dragon Road accepts at most one Steel Dragon recruit
per clear, the record's 25%-spawn guaranteed recruit; none of the recovered
flags addresses battle-recruited monsters, and the character identity resolves
from your own decoded name catalog. A duplicate recruit changes nothing,
because no duplicate rule survives.

Experience is the whole point of the Roads: both are species-locked training
zones, Dragon and Machine respectively, and your party keeps the levels it
earns there.

### The world-map Lambda routes give EXP and a bounded Companion drop

The two Chapter-34 world-map routes are single level-80 and level-90 battles
and pay their experience the same way. Unlike the Roads, their sections carry
recovered non-empty `dropBuddies` manifests, and the community record
documents one exclusive Companion roll per battle whose candidate lists match
those manifests exactly. A clear may therefore settle at most one Companion
the stage's own manifest names, minted at level 1. Everything else — Coins,
items, the Luck chest, and the documented
battle-4 character recruit — is still refused, because those channels have no
recovered identities or captures and a plausible invented rule is worse than
an honest refusal.

What is *not* recovered in either family is how much experience: the retired
server validated these totals and no recording survives. So the server bounds
them instead — generously, and derived from the same selector's own tiers
rather than picked. The bound exists to stop a tampered client claiming an
absurd number, not to reproduce a rule.

## Special Quests are separate from Arena VS

After Chapter 3, the guided server advertises the recovered solo Chapter 3003-1
*Money Money Time* card in Arena → Special Quests. It costs 5 stamina and uses a
bounded local Coin settlement policy; it is not a claim about the original event
rotation or rewards.

Guided setup also derives the five recovered archive families from your own
BattleData and character catalog, and enables the fourteen packaged Strikes Back
families. Their permanent progress gates, zero-Coin clears, and first-section
associated-character grants are local archive policy rather than recovered
schedules, probabilities, or complete historical reward tables.

Tower of Temptation is a separate bounded compatibility slice: guided setup
derives the twelve Chapter 9010–9013 floors from your BattleData and advertises
them through the client's dedicated Tower list after Chapter 3. Their permanent
gate and zero-Coin clear are local policy, and original-client clear return
remains unverified.

Melting Pot: Lizardfolk, Beastfolk, and Human are the 45 sections of Chapters
9100–9102, derived the same way and advertised as one folded card per race after
Chapter 3. They settle from the drops the client reports, which is where the
candy items come from — those drops are attached per spawn inside the chapter
programs rather than to the shared enemy records. The community-aggregate
mechanic these chapters' class fields hint at is not reconstructed.

Arena VS, rankings, and multiplayer remain disabled rather than presenting a menu
that cannot complete.

## Eidolons are not a missing final-version battle mechanic

Version 5.5.0 retired Co-op/VS, the in-battle Eidolon charging gauge, and Tavern
Eidolon enhancement. The final 5.5.7 client therefore does not need those systems
for solo play. Owned Eidolons remain collectible entries under Options, and the
former Co-op Eidolon quests were converted to single-player quests.

Guided setup enables the **12 battle/banner-backed solo Eidolon stages** in
Chapters 4100–4111. The sixteen zero-battle Eidolon tier placeholders are
deliberately excluded, and their older Co-op reward records are not reassigned to
the final solo stages without a matching result capture. Availability after
Chapter 3 is permanent local archive policy, not a recovered historical rotation.

Guided setup does not enable the retired enhancement route. The server-only
launcher also leaves it disabled by default; archival analysis can still opt into
`bootstrap_server --summon-skills` explicitly.

## Emulator caveats

Graphics and sound are both unreliable under emulation and neither problem comes
from the server. A physical device is the better choice if you care about either.
See [Emulator setup](emulator.md).
