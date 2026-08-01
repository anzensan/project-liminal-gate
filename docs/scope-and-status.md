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

The exact `kind=20,count=1` form spends one Item 81 Fellowship Ticket before
Coins, for either an ordinary Fellowship draw or its `luckType=true` Fate
variant. Mixed ticket/coin batches, campaign Pacts, and event-specific Pacts
remain unsupported.

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
| Tower of Temptation 9100-1 | Chapter 3 |
| Shin'en Lambda and Mutoh Lambda (world map) | Chapter 34 |

Those thresholds are local preservation policy, not recovered schedules. The
retired event and Hunting rotations were not captured, so the standard setup
makes each row permanent after its story gate. **Empty optional screens on a new
account are expected, not a fault.**

The last row is the exception: the two world-map points after Chapter 34 are the
client's own gate, not a policy this project chose, and their five battles each
open one at a time.

### The Roads give EXP and nothing else

**Dragon Road and Machine Road pay experience only** — no Coins, no items, no
Companions.

That is not a limitation this project chose. Both switch the other channels off
in your own copy of the game's data: each declares an empty Companion drop
list, sets `allowLucky` to 0 so no Luck chest is ever offered, and sets
`doNotDropExchangeItem`. The game itself says these stages drop nothing. A
clear that claims otherwise is refused rather than settled, because the claim
would have to come from somewhere other than the game. The community record
describes retired-service rewards for both (a Steel Dragon recruit; Star
drops); those claims are recorded in the reference ledger and deliberately not
applied, because the recovered declarations outrank an external table.

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
items, the Luck chest their own `allowLucky` 0 rules out, and the documented
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

The first Tower of Temptation floor is a separate bounded compatibility slice:
guided setup derives Chapter 9100-1 from your BattleData and advertises it
through the client's dedicated Tower list after Chapter 3. Its permanent gate and
zero-Coin clear are local policy, and original-client navigation and clear remain
unverified. The other 44 recovered Chapter 9100–9102 floors stay unavailable.

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
