# External quest reference ledger

Status: operator-approved community/reference sources. These sources are
useful for defining local preservation policy, but are not Mistwalker service
captures or client-transport proof. A source entry never replaces the need for
a recovered client chapter/section, selector, and bounded settlement contract.

## Sources

- Terra Battle Wiki, [Hunting Zone](https://terrabattle.fandom.com/wiki/Hunting_Zone):
  Hunting families, final Huntland placement, and entry stamina.
- Terra Battle Wiki, [Attack of the Coin Creeps](https://terrabattle.fandom.com/wiki/Attack_of_the_Coin_Creeps):
  zone and Arena Lv. 35 entry/reward ranges.
- Terra Battle Wiki, [Metal Zone](https://terrabattle.fandom.com/wiki/Metal_Zone):
  final Huntland entry forms, stamina, roads, and zero Coin/item behavior.
- Terra Battle Wiki, [Crystal Road](https://terrabattle.fandom.com/wiki/Crystal_Road):
  seven-stamina entry and published item/Metal Ticket reward table.
- Terra Battle Wiki, [Special Quest category](https://terrabattle.fandom.com/wiki/Category:Special_Quests):
  the named Arena -> Special Quest inventory.
- Tester menu record, issue 62: the Arena and Huntland menu tree as it stood in
  5.5.7 at shutdown, card by card, with the rows this archive serves that the
  final menus did not list called out separately. It is a first-hand record of
  a running client rather than a community summary, and it is what established
  that Arena -> Descent Quests is a menu of its own and that Battle Champs and
  8-Bit Rush belonged in Special Quests. It states menu placement and card
  names only; every economic and reward fact behind those cards still comes
  from the client and the operator's own master data.
- Terra Battle Wiki, [Items](https://terrabattle.fandom.com/wiki/Items) and its
  per-item subpages: the item categories and each item's drop locations. Its
  "Power-up items" category names the same eight items the client's own
  `ItemData.kind` marks `HelpItem`, and its "Candy items" category the same
  seven marked `UsableItem`, so the two records corroborate each other rather
  than either being taken on trust. The subpages are the only surviving record
  of where candy and the four Reinforcements came from (Tower of Temptation
  milestones, Melting Pot Lizardfolk, Ultimate Five); none of that is
  implemented, and it is the only route to it if it ever is.
- [Terra Battle Stats](https://tbs.desile.fr/): external stage/drop/Metal Zone
  reference application. Its publicly served stage dataset is an older 4.6-era
  snapshot, so it cannot establish a final-version Crystal Road or Chapter
  3003 client identity. Its open stage data covers story chapters 1--38 only;
  it carries no 2000-series event rows.
- Terra Battle Wiki, [Mutoh Λ (Quest)](https://terrabattle.fandom.com/wiki/Mutoh_%CE%9B_(Quest))
  and [Shin'en Λ (Quest)](https://terrabattle.fandom.com/wiki/Shin%27en_%CE%9B_(Quest)):
  the Chapter-1100 map specials' per-difficulty drops, whose Companion
  candidate lists match the recovered `dropBuddies` manifests exactly.
- Terra Battle Wiki, [Dragon Road](https://terrabattle.fandom.com/wiki/Dragon_Road)
  and [Machine Road](https://terrabattle.fandom.com/wiki/Machine_Road):
  Steel Dragon recruit and Star/Mech Skill Drop rewards.
- Terra Battle Wiki, [Daily Quests](https://terrabattle.fandom.com/wiki/Daily_Quests)
  and its per-quest subpages: rotation history and per-quest drop rules.
- Terra Battle Wiki, [Pact of Truth](https://terrabattle.fandom.com/wiki/Pact_of_Truth),
  [Pact of Fellowship](https://terrabattle.fandom.com/wiki/Pact_of_Fellowship),
  [Pact of Fate](https://terrabattle.fandom.com/wiki/Pact_of_Fate),
  [Luck](https://terrabattle.fandom.com/wiki/Luck), and
  [Companions of Truth](https://terrabattle.fandom.com/wiki/Companions_of_Truth):
  displayed recruitment rates, duplicate gains, and Luck caps.
- Archived official news, [v5.5.0 announcement](http://web.archive.org/web/20181223215307/http://www.terra-battle.com/en/news/2018/10/ver-550.html)
  and [recruitment-rate display announcement](http://web.archive.org/web/20180228133231/http://www.terra-battle.com/en/news/2018/02/post-156.html):
  dated launch of the fixed Trading Post rotation and of in-game rate display.
- Terra Battle Wiki, `Trading Post/Trades/Rotation` revision history
  (revisions 83575--83859): the dated Friday-by-Friday edit trail that fixes
  the rotation phase.
- Terra Battle Wiki, [Achievements](https://terrabattle.fandom.com/wiki/Achievements),
  [Tower of Temptation](https://terrabattle.fandom.com/wiki/Tower_of_Temptation),
  [Weekly Challenge](https://terrabattle.fandom.com/wiki/Weekly_Challenge),
  Descent Quest pages, and [Battle Champs](https://terrabattle.fandom.com/wiki/Battle_Champs):
  reward tables recorded in `findings.md` for future boundaries; none is
  implemented from the reference alone.

## Reconciliation with the bundled policy

| Family | Client identity | Reference-backed facts used now | Status |
| --- | --- | --- | --- |
| Pudding Time, Tin Parade, Puppet Show | 1001--1004, sections 1--3 | Huntland placement and 5/8/10 entry stamina | Implemented; item ceilings remain recovered/local policy as labeled in the catalog. |
| Attack of the Coin Creeps | 1003, sections 1--3 | 10/15/20 stamina and 1,500/5,000/11,000 maximum listed Coin ranges | Implemented; these match the existing bounded Coin policy. |
| Metal Zone and Roads | 3000 sections 1--7 and 11--17; 1200-1/1201-1 | ticket-or-stamina entry, 5/8/10/13/15/18/20 costs, zero Coins/items, and road costs | Implemented; EXP ceilings remain local anti-inflation bounds because neither source gives a complete client-clear contract. |
| Money Money Time / Arena Coin Creeps Lv. 35 | 3003-1 | 5 stamina, three battles, and a 1,200--1,500 listed Coin range; Issue 25 final-client clear reported 1,800 | Implemented as a bounded default Special Quest; the client-observed 1,800 overrides the incomplete external ceiling. Permanent availability remains local policy. |
| Crystal Road | 3004-1 | Final APK BattleData title, three battles, and 7 stamina; reference table's one material item plus 20% Metal Ticket/conditional power-up channel | Implemented as a permanent local Huntland route after Chapter 3. It accepts at most two items: one of client Items 1--17, plus at most one of Item 50 or power-up Items 53--56. The retired service's probabilities are not reimplemented or claimed; original-client acceptance remains the next boundary. |
| Curated Archive | 42 stages across 2000--2011 and 2014--2018 | Final-client flags and selector identities, BattleData sections/economics, compiled chapter programs, archived backgrounds/banners, and eleven character associations | Generated by guided setup from matching user-local inputs. Permanent story gates, zero fixed clear-Coin increments, and first-section associated-character grants are local policy; variable battle Coins are client-reported. Jade Dragon 2004-1 clear is client-confirmed; other Archive clears remain unverified. Test Chapter 2012, bannerless Chapter 2013, and empty 2015-4--6 placeholders are excluded. |
| Battle Champs, 8-Bit Rush | 8008--8011 sections 1--2 and 8018-1 | The shutdown menu record places all nine stages in Arena -> Special Quests and names each card | Implemented. Their identities come from the final client's own banner artwork rather than the reference or the BattleData titles, their section economics from BattleData, and their Companion ceilings from their own `dropBuddies`; the Chapter 19--23 gates are local archive policy. |
| Other Arena -> Special Quests | Per-stage unknown | The category identifies named pages with branch/recruit conditions | Not enabled without a final-client identity, packaged resources, and a bounded reward/recruit contract. |
| World Map Specials (Mutoh/Shin'en) | 1100, sections 1--10 | One exclusive Companion roll per battle; per-battle candidate lists match the recovered `dropBuddies` manifests exactly | Implemented as bounded acceptance: at most one manifest Companion per clear, level 1. Coins, items, Summons and the battle-4 character recruit now settle from the client's own report, since it is the only party that knew what its battle dropped. Roll weights and the difficulty schedule are recorded, not implemented. |
| Dragon Road / Machine Road | 1200-1 / 1201-1 | Steel Dragon monster recruit; three to five of one random Star per machine plus a Messages-borne Mech Skill Drop | Implemented as bounded acceptance where the recovered flags leave the channel open: Dragon Road accepts one Steel Dragon recruit (character 1090, operator-resolved), Machine Road accepts Stars 118--121 under a generous ceiling. Companion drops and the Luck chest stay refused on the recovered flags' authority; the Mech Skill Drop has no recovered identity. |
| Daily Quests | 6000--6012 | Per-quest drop rules, the two Puzzle Quest Companion drops at 60%, and the final 41-day double-quest rotation | Crystal Roundelay bounds power-ups 53--56, Rarity Rumble bounds Item 81 and the four Ores 26--29, and Tearjerker Time bounds its Tears and attribute rings. The Puzzle Quest Companions are not taken from the record at all: 6011-1 and 6011-2 are the only two stages carrying a `dropBuddies` manifest, and it decodes to Companions 267 and 140 at one copy each, which the record then corroborates by name. Roll odds stay the client's. Rotation is client-scheduled; the once-per-UTC-day rule is unchanged. |
| Trading Post | Server-fed | Dated revision trail fixes the rotation phase; the archived 5.5.0 news dates week one | Implemented: the cycle is anchored to Friday 2018-10-05 00:00 UTC. Continuity to end of service rests on edit silence, not a capture. |
| Pacts / Companion draw | Server-owned | Displayed rates: Truth 4/10/15/71; Companions of Truth Z 3 / SS 8 / S 10 / A 30 / B 49; Luck caps 100/80/70 | Truth shares and duplicate gains corroborated exactly. Companion draw stays uniform: the public bundle has no per-ID rarity map; a weighted operator catalog is the sanctioned path. |

## Promotion rule

Promote a row only after all of the following are present:

1. recovered final-client chapter/section and selector/flag behavior;
2. resources supplied by the tester-local manifest;
3. a bounded start/clear contract covering every reported reward channel;
4. real-HTTP rejection, replay, and restart tests; and
5. original-client acceptance.

Do not use an external reward table to create a generic success response, to
infer a missing chapter ID, or to enable a collaborative/PvP path.
