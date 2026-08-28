# Changelog

## Unreleased

Every gameplay fix below needs a server restart; on-device testers need a rebuilt
APK. None of them needs the event catalog regenerated — the folded-card
identities are applied when the catalog is loaded, exactly as the class limits
and the Descent menu already are, so a catalog generated before this still
draws the cards the final client drew.

The setup and documentation changes at the end need neither a restart nor a
rebuild: they are build-computer behaviour, and take effect the next time you
run the command.

### Added

- **The iOS client can play against this server, sharing one save with an
  Android device.** It needs a server restart and no APK rebuild: this is the
  dedicated-server route only, and the on-device package is unaffected.

  The Android client is patched to ask this server directly. The iOS one
  cannot be — its executable is FairPlay-encrypted, so the URLs compiled into
  it are unreadable — and it only ever asks for the two hostnames the retired
  service used. So the client is left alone and the names are redirected
  instead, which works because it validates no certificate at all.

  `liminal_gate.ios_front_end` answers those two names, terminating TLS on 443
  and serving cleartext on 80, and relays both to the server unchanged. It
  parses no game request and decides nothing; the server remains the only
  authority. A service template that grants it `CAP_NET_BIND_SERVICE` rather
  than root is in `deploy/`.

  One server now answers both clients at once, because each asks on its own
  URL base — Android on `/resources/`, iOS on `/gdresources/data_u2017/iOS_2/`.
  The two resource trees must never share a base: the 32-hex prefix on a
  resource filename hashes the asset's logical name rather than its contents,
  so both trees spell every filename identically while holding different
  bundles, and a merged mapping would serve one client the other's data. An
  overlap between two manifests is refused rather than resolved.

  The iOS tree is picked up automatically beside the Android one at
  `local-input/resources/data_u2017/iOS_2`, or named with
  `--ios-resource-root`. A host without one is unaffected, and so is a host
  whose copy is missing or half-extracted: it serves Android and says why it
  is not serving iOS. Only an operator who named a tree explicitly gets a
  failure, because a mistyped path must not look like a host that simply has
  no iOS files.

  Sharing a save needs no new mechanism. A device that has talked to another
  server goes straight to login and is refused with `unknown_local_account`;
  `account_state link` attaches its UUID to an existing account, which both
  admits the device and shares the progress. It is handoff rather than
  simultaneous play. [Play on an iPhone or iPad](docs/ios-client.md) covers
  the DNS, firewall, and certificate steps, and what each failure looks like.

### Fixed

- **A quest with no chest still answered with one, empty.** A tester on issue
  77: *"there are sounds effects and you have to tap through it"* for a chest
  screen that never appears. The entry sent `luckResult` and `luckUpTable`
  together whenever *either* had something, so every chestless stage that
  granted Luck shipped six empty slots — "here is a chest" with nothing in it,
  the same shape of placeholder the empty `buddyInfo` was. Cryptid Forest does
  it on every entry with a below-cap party: the record names it chestless and
  it is an `allowLucky` chapter, so the gain always fires and the chest never
  can. The two fields now travel on their own terms.

  An absent `luckResult` is the well-tested shape rather than a new one — most
  of the game documents no pool, so most entries have always answered without
  it. What is new is a gain travelling alone, and the two are independent keys.
  This could not be settled statically: il2cpp string literals resolve through
  a metadata index rather than an address in this binary, so no scan finds
  which client method reads either field, and the argument rests on the field
  already being routinely absent.

  **This does not explain the Yamamoto's Puzzle Quest report.** Chapter 6011
  has no documented pool, donation is off on the Huntland route, it is not an
  `allowLucky` chapter, and Daily Quests cost no stamina — so no Luck ever
  rolls there and the entry answers with neither field, verified over HTTP. A
  chest sequence playing on that quest is the client's own, and nothing this
  server sends starts or stops it.

- **A Luck chest's Companions did not survive the battle that paid them, and
  the ones that did arrived at the wrong level.** Both from the same tester on
  issue 77: *"Luck chests now appear on daily quests at least, but rewards
  don't stick around"*, and *"for some reason the rewarded OII companions are
  shown as being rewarded level 30, even though they should only be level 1."*

  The first is an ordering defect in all three settlements. The battle's own
  Companion-drop projection was built *before* the chest was granted and then
  assigned over `buddyInfo` at the end of the clear, so every Companion a chest
  paid was thrown away whenever the same battle also dropped one. Even when it
  did not, the answer carried that projection rather than the account's own
  box — and `UserData.LoadBuddyInfo` resets the client's box and refills it
  from what arrives, so the client was handed a box the chest's Companions were
  missing from and its next Companion write persisted their absence. The chest
  grant is now the last writer, and the answer carries the account's own box
  whenever either source granted, which is what the Companion sale and
  strengthen routes already do.

  The second was ours, not the client's — the client was right. `BuddyData`
  carries a `DropLevel` per Companion, and it is exact: 446 of the 497 master
  records say 1 and the other 51 say 30. The 51 are precisely the ΟⅡ
  Companions, whose base Ο form drops at 1. This server had been minting every
  dropped Companion at a literal 1, on the reasoning that `EnemyData` records
  which Companion drops and at what rate but no level — sound about `EnemyData`
  and looking straight past `BuddyData`. So the result screen showed the
  client's 30 and the box held a level 1 copy. Recovered into
  `companion_master_data.companion_drop_level` and used by every drop site.

  The story drop channel reads its levels from the generated story-outcome
  catalog, so that half needs the catalog regenerating to pick the ΟⅡ levels
  up; the chest, Huntland, side-world and Chapter-1100 channels take effect on
  restart.

- **Shin'en and Mutoh paid no Luck Treasure Chest at all, and the three Dragon
  Kings paid the wrong one.** Both halves of issue 77's remainder, both
  reported by the same tester: *"I just completed some special battles (Shin'en
  HM, Mutoh HM, and the 3 Dragons King Descended), and there were no luck-based
  chests"*, then, once the Dragon Kings had one, *"Can we have informations
  about luck chest rates 80 and 100? This does not necessarily seem to match
  the data from the Terra Battle sources here."*

  The Chapter 1100 World Map Specials are their own handler, and it was the one
  the last round did not reach: it never rolled a chest, sending six empty slots
  under a comment calling that local policy. It was not policy — Chapter 1100 is
  not on the record's own chestless list, which names the Hunting and Metal
  zones and eleven quests and no map special. It rolls one now, the clear
  expects the Coins it paid, and the Companion and character forms are granted
  by the server as they are everywhere else. Donation is left switched on here,
  unlike the Hunting entry, because Chapter 1100 is documented by neither the
  chestless list nor a recovered table — so a nearby chapter fills a silence
  rather than answering over the record.

  The Dragon Kings were a different gap. Chapters 2009–2011 had no recovered
  chest table and were being paid a donated Chapter 36 chest, which is why
  their Luck 80 and Luck 100 bore no relation to their own pages. Seven
  2000-series quests are now recovered from the record: the three Dragon Kings,
  the Bahamut, Leviathan and Odin descents, and Lucia the Explorer. Their pages
  carry plain tables under a plain heading — no template is involved, so the
  blind spot that hid Strikes Back is not the reason these were missing; they
  were never in scope. Every name on all seven resolved exactly, and the joins
  are confirmed rather than taken from the page titles: the three descents pay
  the character ids their own recovered manifests already name, and the two
  Lucias in the master data are separated by this project's own recovered
  recode recipe rather than by guesswork.

  Five chapters are deliberately still donated. The Last Story and Yamamoto's
  Puzzle Quest carry no chest section; Final Fantasy XV and Royal Rings
  Descended carry one table per section with nothing joining a caption to a
  section ordinal — the anchor Lucia's numbered tables do have; and chapter
  2017 has no identified wiki page at all. A table filed under the wrong
  section is worse than a donated one.

- **Recoding a character you were fielding left a level 1 copy of them stuck in
  your squad, and then refused every save that tried to remove it.** A tester
  described the whole shape of it: *"the character won't be removed, but they
  are reset back to level 1 with 0 SB and luck and as soon as you remove that
  character from all teams, they will disappear."*

  The stand-in is the client's own. The recode answer is read by
  `AppServerUtil.<Rebirth>...<>m__0` (ARM64 `0xFBCD00`), which takes
  `buddyInfo` and `chrdata` and nothing else, and the main squads are rebuilt
  only inside `LoadUserdataFromJson` — reachable from `GetUserData` and
  `GetUserDataAfterClose`, both called only by `LoginAndUpdate`. So the client
  goes on naming the character the recode just consumed until the next launch,
  its team screen resolves that slot through `GetCharacterByID(id, create:
  true)`, and a fresh level 1 `Character` with no Skill Boost or Luck is minted
  straight into the player's roster. **No response this server can send
  prevents or repairs that**, which is why the recode is refused instead.

  A character any main squad fields can no longer be recoded, used as a
  material, or spent as the substituting Joker. This is a **deliberate
  deviation**: `RebirthErrorCode` has no value for "in a party" and
  `UIChrSelectWindow.GetFilteredList` filters the recode picker on
  `HasRebirthInfo` alone, so the retired service almost certainly allowed this
  and produced the same stand-in. The release picker in that same method is the
  one that skips `IsInAnyTeam`; the recode picker never got it. Bench the
  character and the recode proceeds exactly as before. Versus squads are not
  refused, because `IsInAnyTeam` does not read them and `LoadChrData` repairs
  them from the answer.

  The second half was worse than the stand-in. The team screen marks what it
  draws dirty, so `SendDirtyData` posted the stand-in's row back, and a
  submitted roster row naming a character the account does not own refused the
  *whole* save — including the party edit that would have cleared the slot. An
  account that had already hit this could not repair itself from the client at
  all. Such a row is now dropped and the rest of the save lands, which is the
  rule the party half already followed and for the same reason. It grants
  nothing: a submitted row is only ever merged over a row the roster already
  holds. The dropped ids are recorded in the event log, because the same shape
  is what a genuine roster desync looks like.

- **Half of every Companions of Truth pull was Healing Wand or Regen Bangle.**
  A tester counted it: *"most 10 pulls are like 5-6 of just those two items …
  a statistically unlikely amount"*. A second confirmed the shape of it from
  the other side — *"I did a few hundreds of pulls and the only B I got were
  those. I thought that was the only two options in B frankly."* They were.

  The Rare pool follows the displayed class shares, and B carries 49% of a
  pull split evenly across its members. The bundled roster had two members in
  B, so Healing Wand and Regen Bangle were 24.5% each: 4.9 of them in an
  average ten-pull, which is what the count reported.

  The roster was wrong because `SlotKind` is not a partition of the two
  Companion pools, and it was read as one. Every A- and B-class Companion is
  offered by *both* draws — the Companions of Fellowship page says so
  outright — and those shared records carry neither `kind == 1` nor
  `kind == 2`, so taking the Rare pool to be the `kind == 2` records returned
  the Truth-exclusive members only. Z, SS and S came out exact at 19/13/50,
  which is why the error survived review; A arrived 26 short and B 37 short.
  The same 64 Companions were missing from the Coin pool, which had been
  serving C and D alone, so the whole shared tier was unobtainable from either
  draw.

  Both rosters now come from the two pool pages rather than from the slot
  field: Truth is 177 members (Z 19, SS 13, S 50, A 56, B 39) and Fellowship
  is 145 (A 26, B 38, C 41, D 40), overlapping by the 63 the pages share.
  Healing Wand and Regen Bangle fall from 24.5% to 1.26% each, and A-class
  members from 1.0% to 0.54%. Existing boxes are untouched; only future pulls
  change.

  The Fellowship pool still selects uniformly, and that is now a weaker fit
  than it was: no displayed-rate record survives for it, and uniform over a
  roster spanning four classes returns A, its top class, at 17.9%. Recorded in
  `companion_draw_catalog.py` as a known gap rather than reconstructed, since
  inventing a four-class table would be a claim about retired odds nothing
  supports.

- **The Coin pool was a better source of A-class Companions than the Energy
  pool.** A follow-on from the roster fix above rather than a separate report.
  Restoring the shared A/B tier to the Companions of Fellowship pool left that
  pool selecting uniformly over 145 members, which put a given A Companion at
  0.690% on a 2,000-Coin pull against 0.536% on a 3-Energy one. A and B are the
  same Companions in both pools, so that made Truth the wrong place to chase
  every Buckler, Chronicle and Mythril piece in the game.

  The Normal pool now carries class shares of its own: A 8%, B 12%, C 30%,
  D 50%. No displayed rate for it survives — the 2018-02-28 announcement and
  the Companions of Truth page cover the Rare pool only — so unlike the Rare
  table this one is chosen policy, and what chooses it is a property of the two
  pools rather than a guess at retired odds. The shared tier is given 20% of a
  Coin pull against the 79% it carries on Energy, and each tier is split in the
  30:49 the Rare record states for its own bottom two classes. Energy now beats
  Coins for all 63 shared Companions — 1.74x on A, 3.98x on B — which is
  asserted as a property, so retuning either table stays free as long as the
  ordering holds. The table is tunable as `companion.normal_class_share_ppm`.

- **A Companions of Fellowship pull cost 3,000 Coins instead of 2,000.** Both
  the price the client displays (`NormalBuddySlotCoins`, sent in the constants
  block) and the price the draw route charges (`BUNDLED_COIN_COST`) are server
  policy, and both were set above the figure the Companions of Fellowship page
  records. They now read 2,000 and must stay equal to each other.

- **Luck was paid to Squad 1 whichever squad you fought with.** Three testers
  reported it from three directions: *"Luck gains in metal zones still dont
  stick"*, *"Luck doesn't stick period — doesn't work on normal stages
  either"*, and a screenshot of Squad 3 where the results screen had announced
  a gain for one character and a different one had it afterwards — *"violet was
  3.1 and went to 3.4 (the 0.3 bahl was supposed to have gotten), so maybe it's
  a positioning thing"*. It was.

  `teamMembers` is every squad the account keeps flattened into one array, and
  `teamNo` names the one on screen. The Luck runtime read the first six
  entries, which are Squad 1 no matter who is fighting. So a party fielded from
  Squad 3 had its chest odds averaged from a squad that was not playing, its
  growth rolled against the Luck and the class ceilings of characters that were
  not there, and the gain paid to those characters instead. `luckUpTable` is
  positional and the client applies it to the squad on screen, which is why a
  character sitting in both squads at different slots took a gain announced for
  someone else — the "positioning thing" the third tester saw.

  Nothing about this was particular to the Metal Zones. It looked that way
  because a Metal Zone run is what a player keeps a second squad for: the
  levelling party is Squad 2 or 3 and the story party is Squad 1, so the same
  account saw Luck stick on the story and never in the zones. An account that
  has only ever had one squad was never affected, which is why the suite did
  not catch it — every party in it was a single squad, the one shape where the
  front of the array *is* the party.

  All three Luck decisions now read the squad on screen, through the same
  resolver the species and class gates and the EXP multiplier already used.
  Luck already earned is not recomputed: what a wrong squad was paid, it keeps.

- **One Joker Λ covered a Recode's whole monster bill, at any level.** A tester,
  on what it should do: *"Joker^ should be usable as a wildcard Component that
  can replace any 1 other unit you might have. I'm not sure if this is working
  as I don't have my Joker^ above level 50."* It was not working, in both
  directions at once — and the level they were waiting to reach was never being
  asked for.

  The record states the rule twice. [Recode DNA](https://terrabattle.fandom.com/wiki/Recode_DNA)
  lists "Two specific Monsters at level 50 or higher", and under them "Joker Λ
  can be used as a replacement for **one** missing or under-leveled monster";
  [Joker Λ](https://terrabattle.fandom.com/wiki/Joker_%CE%9B) says it from the
  other side — "In order to be used as a replacement, Joker Λ must be at level
  50 and one of the two material monsters must be under level 50 or not
  recruited." This bundle tracked whether *any* monster fell short as a single
  flag, so one Joker at level 1 satisfied a recipe the account held neither
  monster for.

  A Joker now stands in for exactly one monster and must have reached level 50
  itself. A second shortfall, or a Joker below 50, is `NotEnoughMons` (4) like
  any other — `NotEnoughMonsButCanUseJoker` (7) is an offer, and is only made
  when it would be honoured.

  The monster a Joker replaces also survives now. It was being consumed
  alongside the one that was actually spent, so an under-level monster the
  Joker stood in for was destroyed by the recode that did not use it, taking its
  squad slot with it. It keeps its place and its Luck; the Joker is the material
  in its stead, so the Joker's own fifth of Skill Boost and Luck is what carries
  into the recoded unit.

  Recoded units already have a Luck ceiling of 100 — every one of the 65 recipes
  produces a Λ, and a Λ reaches the maximum whatever class it came from — which
  is what the per-character ceilings released in 1.1.0 already say for all 65 of
  them. Reported alongside the Joker; nothing needed changing for it.

  No save changes: nothing already recoded is revisited.

- **A "+" Pact levelled the first job and no other.** The second half of
  [#69](https://github.com/anzensan/project-liminal-gate/issues/69): *"when I
  pull a +Pact, only the additional levels appear to be added to the first job
  (only)."* The duplicate gain itself was fixed in 1.1.0 to raise every job the
  character has unlocked; the "+" that decorates it kept writing slot 0.

  It carried both halves of the defect that fix removed. The extra levels landed
  on the first slot whatever else was unlocked, and the reply was overwritten
  with slot 0's level while still naming the *active* `jobID` — so a character
  whose active job was its second was told that job had reached a level
  belonging to a different one. Both grants now go through one
  `_raise_unlocked_jobs`, since it is one rule: a duplicate raises the
  character, and the character is all of its jobs.

  This one had been reported by a test before it was reported by a tester.
  `DuplicateJobLevelTest` failed about one run in five, and the fix applied on
  2026-08-09 was to turn the "+" roll off for that class — the random gain
  looked like the flake, when it was the roll landing where it should not. The
  new `PlusPactJobLevelTest` forces the roll to 100% and asserts what it does to
  a two-job roster row, which is the assertion the old guard was avoiding.

  No save changes: levels already granted stay granted.

- **The Companion box stopped at 250, and a full box locked every stage that
  could drop one.** Reported by a tester storing Metal Minions to strengthen
  Companions: at 250 the counter turned red — 251 out of 250 — and Metal Zone
  would no longer start. The wiki's [Companions](https://terrabattle.fandom.com/wiki/Companions)
  page records 1000 as the final 5.5.7 limit, and this server had been settling
  Companion drops against 1000 all along.

  The number reached the client under the wrong name. `SetServerConstants`
  reads a fixed list of key names, and the one it reads for the Companion box
  is `BuddyBoxMax`; this bundle sent `maxBuddyBoxCount`, which is the name of
  the *field* that key sets. A constants key the client does not recognise is
  ignored rather than refused, so the box kept the client's own built-in
  default of 250 and nothing anywhere said so. The client owns this gate: it
  compares its box against the number it was told and withholds the stage, so
  every server-side ceiling agreeing on 1000 could not help.

  `BuddyBoxMax: 1000` is now sent. Existing saves are untouched — a box already
  past 250 stays as it is and is now inside the ceiling the client knows about.

  Two things came out of the same reading of the client. `maxCharacterCount`
  was also being sent and is also not a key the client reads: its roster
  ceiling has always been its own default of 1024, so that key is dropped and
  no account changes. And the full list of names the client does read is now
  recorded beside the block and asserted against what is served, so a key this
  project invents or mistypes fails a test instead of going quietly nowhere.

- **A Recode did not consume its monsters, and could be run against a
  destination already at maximum Luck.** Two testers reported keeping monsters
  a recode should have taken — "Snaptrap and Phi Orbling still here max luck
  still and level", "I still have Megacell maxed out and Chiton at level enough
  to recode. Just Leviathan normal is gone from my roster."

  The record: "The two monsters will also be lost upon recoding, and may be
  recruited again through the usual methods." This bundle kept them on the
  roster and instead recorded their ids in `rebirth_used_material_ids`, barring
  every later recode that named the same monster. That substitute was wrong
  twice over — the monsters stayed, and the bar closed a loop the same record
  describes, where a recoded character is recoded *again* to raise its Skill
  Boost and Luck with monsters raised again in between. A second recode of any
  recipe was unreachable.

  The monsters are now consumed, and so is a Joker Λ standing in for a missing
  one. Any squad slot naming a consumed monster empties, the same way the
  source's slot already followed the transformation — the client keeps monsters
  out of squads before it will offer the recode, but a consumed character a
  squad still names is the exact damage this route has done before. A Companion
  a consumed monster carried is unequipped and stays in the box.
  `rebirth_used_material_ids` is left in existing saves and no longer read or
  written; nothing is taken from an account that already recoded, so monsters
  kept by the old behaviour stay kept.

  The ceiling on repeat recoding is the rule that bounds it in the record:
  "Recoding is not available if the recoded character is already at 100 Luck."
  A destination already at its cap is refused before anything is spent — the
  source and both monsters are still there to try again with. `Character.CanRebirth`
  reads `luck` against `luckMax` ahead of coins, items and monsters, so the
  client withholds the option itself and a request that arrives anyway is a
  stale menu; no error code says "already maxed", so it is answered as the
  recipe not being available, which is what that code already means here.

- **A Recode carried no Luck from its material monsters.** Reported by a tester
  who recoded with a Megacell at its 70.0 cap, expected a fifth of it — 14.0
  Luck — to come across, and got none.

  The record gives one proportion and applies it to both carried values: a
  fifth of each material monster's Skill Boost, and a fifth of each material
  monster's Luck. This bundle implemented the first and not the second. The
  omission was in the transcription rather than the arithmetic — the rule was
  never written down beside the constant, so nothing disagreed with it, because
  nothing else held it. The source's own Luck, the source's own Skill Boost, the
  5 Luck an already-owned destination gains and every ceiling were all already
  right; only the material share was missing.

  Recodes already made are not recalculated. There is no record of what a
  material's Luck was at the time, and inventing one would grant Luck this
  project made up.

- **A Recode gave the rebirthed unit the equipped job slots of the character it
  replaced, and the party screen could not draw it.** This is the cause of the
  report below; the three defects there are real and fixed, but this is the one
  the reporting account was actually stuck on, and its save settled it.

  `jobSlots` is per job. A recode destination is a *different character* with a
  different job list — one job rather than three, for 64 of the 65 bundled
  recipes — but the destination row was built by copying the source's row and
  resetting only `jobLevels`, `jobID` and `buddy`. The array of equipped slots
  came across untouched, so the rebirthed unit carried slot data standing
  against jobs it neither has nor has unlocked, and the client reads a slot
  against the job that owns it.

  In the reporting save that row was the only anomaly in 170: Bahl Λ, one job,
  carrying all three of Bahl's slots. It sat in third place in the squad on
  screen, and the party screen drew the two members ahead of it and then
  nothing — the four rows below kept their unpopulated placeholder, which is
  why they all read as the same Japanese-named level 99 character.

  The rebirthed unit now starts with no equipped slots, exactly as a granted
  character does. A destination the account already owned keeps its own slots,
  active job and Companion instead: they are choices it made for jobs it
  actually has, and a level 1 row has nothing to say about any of them — which
  also leaves its Companion link whole, so only the departed source's is
  unequipped. A save already carrying the copied slots repairs itself the next
  time the server loads it, and
  `python3 -m liminal_gate.account_state validate` reports the shape by
  character and slot.

- **A Recode left the account unable to change its party, and the character
  list came back drawn on top of itself.** Reported after recoding Leviathan:
  "it softlocks the game and I cant change party members at all", "can still
  play stages with already built teams", and — after taking the recoded unit
  out of the squad — "now it bugged out the team selection as well, so now I'm
  hardlocked". Three defects, all of them in what the recode answers with.

  **The recode told the client it owned no Companions.** The response carried
  `buddyInfo` as an empty `{"list": [], "record": []}`, and that field is not
  decoration: `UserData.LoadBuddyInfo` calls `ResetBuddyList` and
  `ResetBuddyRecordList` and then refills the box from whatever arrived. An
  empty one emptied it. Every character still carrying a Companion then drew
  against a Companion the client no longer had, which is the character list
  that came back scrambled — the same screen the report's screenshot shows,
  rows overlapping and a hole in the grid. The Companion sale and strengthen
  routes have always answered with the account's own box; the recode does now
  too.

  **A Companion was left attached to a character the recode took away.** A
  Companion and its character name each other — the row's `buddy` names the
  inventory id, the Companion's `chrID` names the row — and
  `_valid_companion_equipment` requires both halves. It also judges the whole
  save rather than the part a write touches, so one half-attached link answers
  501 to *every* later party or equip save, for the life of the save. Recode
  broke the link twice over: the source leaves the roster still claimed by its
  Companion, and a destination the account already owned is rewritten with
  `buddy` 0 while its own Companion still names it. Selling a Companion has
  always cleared the row that carried it; the recode is the same event from the
  other side and cleared nothing. Both halves are now unequipped, the Companion
  staying in the box, and a save that already carries a broken link repairs
  itself the next time the server loads it. Nothing is granted or taken.

  **A party naming a lost character is now emptied rather than refused.** The
  client rebuilds `teamMembers` from the server only at login:
  `AppServerUtil.LoadChrData` corrects the versus squads
  (`CorrectTeamMemeber_VS`) and leaves the main ones alone, and
  `CorrectTeamMemeber` runs from `LoadUserdataFromJson` and nowhere else. So a
  recode that removes a party member leaves the client naming it for the rest
  of the session, and refusing that save answered every party change with a
  409 the player had no way to satisfy — which is why removing the unit from
  the squad made it worse rather than better. The slot is emptied instead,
  which is the client's own rule for a slot it cannot resolve, cannot grant
  anything, and lets the edits in the same save stick. The server-side
  retarget that points the slot at the rebirthed unit is unchanged.

  `python3 -m liminal_gate.account_state validate <save>` now reports a
  half-attached Companion link by character and inventory id, so an operator
  holding a save can tell whether a "cannot change my party" report has this
  cause without loading it. The server repairs the link on load; the finding is
  for the operator looking at a save before that happens.

- **Quests became unplayable one after another, ending in a Network Error loop
  the player could not escape.** Reported against Metal Zone and All Hail the
  King ([#64](https://github.com/anzensan/project-liminal-gate/issues/64)) and
  described by a second tester as "slowly more quests become affected by this,
  it's always the same way, at first I can do it, but after some time it
  becomes glitched and inaccessible". Both are `hunting_clear_wallet_conflict`,
  and the tester's event log settles both by arithmetic rather than reasoning.

  Two independent defects, each of which refuses a won battle over Coins.

  **A Continue outlived the battle it was spent in, and the server forgot it.**
  The client cannot deduct a Continue's coin cost — it is local policy, and
  what the client thinks it spent is the Energy-shaped `client_cost` — so the
  wallet it reports stays that much above the server's until a settlement hands
  it an authoritative one. `release_abandoned_battle` and every quest start
  zeroed that record, on the reasoning that a new battle starts owing nothing.
  The battle does; the client does not. The log caught three Continues at 100
  Coins each — one spent in a 3000-17 run abandoned for 3000-7, two in the run
  that followed — and the clear reported 806158 against a server holding
  805858, refused four times by exactly the 100 the abandoned run had orphaned.
  Only the three clear paths reset it now, because only they tell the client
  what it holds. Each orphaned Continue was cumulative, which is why more
  quests broke the longer a session ran, and why a relaunch appeared to fix it.

  **A Hunting clear that did not fold its Coins into the wallet was refused.**
  Issue 68 settled this for the core story and deliberately left Hunting alone,
  on the reasoning that Hunting prices are recovered so its arithmetic stands.
  They are ceilings, not prices: `result["coins"]` is the client's own figure
  here too, and Crystal Road declares a zero ceiling while paying 400. On
  All Hail the King 3000-11 the client reported the Coins and EXP of the story
  stage cleared minutes earlier — 423 and 7829, already settled — against the
  wallet it actually held, and the server demanded 423 more than the client
  had, ten times in nine seconds. Both readings are now accepted and the clear
  settles at the balance the client actually holds, so the two cannot drift
  apart afterwards. Metal Zone still pays no Coins: the stale figure is not
  credited, it is simply no longer required.

  Neither defect is in what Chapter 3000 serves. Its two families are identical
  in the reviewed BattleData beyond title and quest text — same stamina, same
  Metal Ticket, same `assumedLevel`, no level sync, class, species or team
  limit — the client registers all seventeen section programs, and both
  families settled cleanly earlier in the same log. The refusals were correct
  answers to wallets the server had made impossible to report.

  Server restart, and an APK rebuild for on-device testers.

- **A played save could be exported and then never imported back, which is
  where moving to a new phone stops.** Reported by a tester transferring an
  account to a second device: every step succeeded — export, `adopt`, the
  account bookkeeping — and the final `import` answered
  `HTTP 413 request_body_too_large` with nothing left to try.

  The save-transfer route was reading its body under `MAX_REQUEST_BODY_BYTES`,
  the four-megabyte ceiling that bounds one client mutation arriving from a LAN
  peer. An import is not that. It is a whole multi-account save, sent from
  loopback, from a file the operator already holds a copy of. Sizing the two
  together made the route asymmetric in the one direction that loses progress:
  the export is a GET and has no ceiling at all, so a save could pass a size it
  could be read out at and never written back at, with the only copy of it on
  the phone being left behind.

  Nothing pathological had to happen to cross that line. A save is dominated by
  the retained replay payloads — 512 per bucket per account, four buckets — so
  a long-played account or two reaches four megabytes on ordinary play. The
  import now has its own ceiling sized for what it actually carries, and
  refuses only a document no save this build wrote could be.

  The receiving device is the one that needs this, so an on-device tester
  transferring an account needs the new phone's APK built from this revision;
  the old phone's build is only ever read from and does not matter. A dedicated
  server needs a restart.

- **Machine Road refused a squad of two Machines, and no squad could have
  passed it.** Reported by a tester who checked the species of every member,
  then levelled them, then tried again with a two-Machine squad — the game
  answered "all members must meet the requirements" every time.

  `teamMembers` is not the party. It is every squad the account has kept,
  flattened into one array, and `teamNo` says which one is on screen: this
  tester's save carries fifteen squads and ninety entries. The client reads its
  party out of that array as `(teamNo - 1) × 6 + slot - 1`. The species lock
  read the whole array, found the Humans and Lizards parked in the other
  fourteen squads, and refused — so no squad the player could build would ever
  have entered, which is why levelling and re-picking changed nothing.

  Every gate and settlement that means "the party" now resolves the squad on
  screen the way the client does. Checked against the reporting save: their
  Squad 14 is Tronic Gal and Chirol, both Machine, and it enters. Dragon Road
  still refuses it, correctly.

  Three more places read the same array and are corrected with it: the Captive
  Golem class band, which had the identical fault waiting; an operator EXP
  multiplier, whose extra share was split across every character in every squad
  instead of the six who fought; and the clear-state audit, whose six-slot
  requirement no real save could satisfy, so it silently never ran — an
  operator who configured that catalog would have had every core-story clear
  refused instead.

- **Tower of Temptation is a row per floor again, because a folded card there
  only ever opened onto floor 1.** Drawing the four bosses as cards was wrong,
  and the reasoning that made it look safe was wrong in a specific way worth
  recording: the client does not expand a folded card by any rule about the
  chapter range it sits in. `UISpecialSelect.GetSectionCount` asks a hard-coded
  table, `sectionNumOfFoldedQuests`, and returns **one** for a chapter the
  table does not name. It names 9010–9013 — the client's own Tower chapters,
  the copy this archive has no tier artwork for — and says nothing about the
  9000–9003 copy served here. So each of the four cards expanded into a single
  tier and floors 2 and 3 became unreachable, with nothing on the wire and
  nothing in the server log to say so.

  The twelve rows are back, each starting and settling exactly as before. The
  shutdown menu did list four cards, and that reading was not wrong — it is the
  9010–9013 copy the client folds, and this archive has no tier artwork for it.
  Twelve reachable floors beat four cards holding one floor each.

  What the client actually declares is recorded now, in
  `client_folded_section_count`, together with the two cards it expands by
  naming their members rather than counting them — which is what makes the
  Battle Champs card eight tiers rather than the five its own range would give
  it. A generated catalog is checked against it, so a card folded onto a
  chapter the client cannot expand fails at build time instead of quietly
  losing its tiers.

- **Tower of Temptation said you did not meet the requirements again, on a save
  that reached it during a session.** Reported by a tester on a fresh save. The
  message is the same one as before and the cause is not: the status block a
  raid quest needs was being sent, but only for the cards that were already
  open when the app logged in.

  The client rebuilds its quest menus from `constants` every time it asks for
  server status, so a card unlocked mid-session appears without a relaunch.
  The raid status block is not like that. The client installs it once, from the
  login reply, and nothing it receives afterwards can add to it. So a player
  who logged in below Tower's Chapter 3 gate and cleared past it in the same
  sitting was handed four cards the login had never described, and every one of
  them answered "You don't meet the requirements to unlock this quest" until
  the app was closed and reopened. A save that was already past Chapter 3 at
  launch never saw it, which is why this survived the first fix.

  The login reply now describes every stage in the raid range the catalog
  declares, whether or not the account can see it yet. The block gates nothing
  — which cards are offered is the menu's business, and the client asks about a
  card only after tapping one it was offered — so what it costs is a dozen
  fields on one reply, and what it buys is that the two halves can no longer
  disagree.

  Closing and reopening the app is still a complete workaround on an older
  build.

- **Battle Champs is one card again instead of four copies of itself.** A
  tester reported the family listed twice: an `Arena -> Special Quests -> Battle
  Champs` card holding the sub-battles, and then `Battle Champs: Fearsome
  Fiends!`, `The Creature From the Void` and `The Dragon Awakens` beside it at
  the same difficulties, names, graphics and costs. They were the same card.
  This server advertised chapters 8008--8011 as a folded card each, and the
  client does not read them that way: the reviewed 5.5.7 metadata carries the
  eight members as literals — `8010-1`, `8010-2`, `8008-1`, `8008-2`, `8009-1`,
  `8009-2`, `8011-1`, `8011-2`, read by
  `UISpecialSelect.GetSectionTitlesIfSpecialFoldedQuest` — in exactly the order
  the shutdown menu record lists them under one `Battle Champs` heading. The
  retained banners say it twice over: all four of `sp8008.bin`--`sp8011.bin`
  read `BATTLE CHAMPS`. One row is served now, and the client expands it into
  all eight tiers itself. Nothing about a tier's start or clear changes. The
  four chapters also share one unlock now, because a card is one thing to
  unlock; the 19/20/21/22 ladder would have opened the card holding two of its
  eight tiers, missing the two the client lists first.

- **Dragon King Descended is one card over its three chapters, and 2010 and
  2011 no longer advertise cards the archive cannot draw.** The same recovered
  literal list holds `2009-1`, `2010-1`, `2011-1` as the members of one card,
  which is what the shutdown menu record shows as `Dragon King Descended` (The
  Primordial, Inexorable and Resplendent Dragon King). Only `sp2009.bin` exists
  as a bare banner — there is no `sp2010.bin` or `sp2011.bin` — so the two extra
  rows were the blank-card failure the Coin Creeps derivation already taught us
  to look for. Their three gates collapse to one for the same reason Battle
  Champs' four do. `Royal Rings Descended` (2016) was already one card and is
  unchanged; both open after Chapter 30, which is archive policy and is why a
  tester below it does not see either yet.

- **Final Fantasy XV is one card holding Gladiolus, Ignis and Prompto instead
  of Gladiolus alone.** Chapter 2015 was advertised as three per-section rows
  and a tester saw only the first. It was unfolded deliberately, and the reason
  was sound while it held: the chapter shipped six sections, 4--6 are the empty
  `空き` placeholders with no battles and no banner, and a folded card carrying
  the chapter flag would have offered all six because `CheckQuestFlag` retries
  an unset `sp_ch_2015-4` as `sp_ch_2015`. The missing half was that folding and
  flagging are separate decisions. The card folds now and its stages carry their
  own section flags, never the chapter flag, so the three placeholders have
  neither a section nor a flag and the client drops them — the same shape Battle
  Champs already used. The retained `sp2015.bin` folded banner is what says the
  fold is what the service drew.

- **The Special Quest list has more headroom.** Battle Champs and Final Fantasy
  XV remove five rows at full progress between them, taking a completed account
  from 29 to 24 against the 30-row ceiling that hangs the client. The Dragon
  King fix spends nothing from that budget — it shortens its own menu, from
  seven rows to five. Tower has a menu of its own and never counted against
  this one.

### Changed

- **Setup says why a connected phone is not ready, instead of reporting it as
  absent.** `adb devices` states every device it can see, and only rows reading
  `device` were kept; every other state was discarded before anything looked at
  it. A phone plugged in and waiting for its **Allow USB debugging** prompt is
  listed as `unauthorized`, so setup said `available: none` — the one thing that
  was not true — and a first-time tester spent half an hour hunting a serial
  number that had been right all along. Each unready state is now named with
  what it means where the tester is standing: `unauthorized` points at the
  prompt on the screen and at the vendors that switch USB debugging back off by
  themselves, `offline` at a USB mode left on Charging, `no permissions` at udev
  rules. An empty list says the same things in the order they fail, and adds
  that `--device` is not needed at all when one device is connected. This
  reaches every route, since all three launchers select their device here.

- **A missing source APK says what the folder does hold.** `no APK at
  local-input/terra-battle-5.5.7-170.apk` was accurate and useless in the case
  that keeps arriving: the file is there, named
  `terra-battle-5.5.7-170.apk.apk`, because Windows Explorer hides a known
  extension and typing the documented name onto a file already called `.apk`
  appends a second one. The tester is looking at the name they were told to use
  and being told it is absent. Setup now lists the `.apk` files beside the
  expected path, and hashes them: a file whose SHA-256 is the reviewed
  5.5.7-170 value is reported as the right file under the wrong name, which
  distinguishes a rename from a re-download — the question that costs the time.
  The double extension is called out by name when one is present. The reviewed
  digest moved to `reviewed_build` so both setup routes can read it; the
  on-device route still requires it, and the emulator route uses it only to
  explain this.

### Documentation

- **Moving a save to a new phone is written down as its own sequence.** Testers
  were assembling it from the cleared-install advice and the `adopt` reference,
  and the two questions that came back are the two the page now answers
  outright: which copy is the untouchable backup and which one you edit, and
  why `--seed-state` cannot be the transfer. That flag embeds a save into an
  APK and copies it only onto an install that has none, so it cannot carry a
  transfer at all — the UUID the save has to name does not exist until the new
  client has run once, and by then the seed no longer applies. The sequence
  also says where `--force` is expected rather than alarming, and what to check
  before using it there.

- **The phone's own settings are documented, and the serial number is not.**
  Four separate device settings can stop an otherwise correct setup — Developer
  options, USB debugging, USB mode set to File Transfer rather than Charging,
  and the separate "Install via USB" switch Samsung and Xiaomi add — and only
  the first two were written down. All four are now listed before the build
  steps on the self-hosted route, with the note that several vendors turn USB
  debugging off again after a period of inactivity, which is why a command that
  worked yesterday reports no device today. The worked examples no longer pass
  `--device`: setup finds a single connected device by itself, and teaching the
  flag as mandatory sent testers looking for a serial before they needed one.

- **Updating is written for people who downloaded a zip.** The instructions said
  to pull a source revision, which is no help to a tester who does not use Git,
  and the warning that matters lived three sections away: the folder must be
  extracted *over*, never replaced, because `user-data/` holds the signing key
  that lets Android update the install in place. Losing it costs the save. The
  update section now says that where the updating happens, keeps the existing
  virtual environment rather than rebuilding it, and notes that a changelog
  entry reading "server restart" still means a rebuilt APK on this route.

## 1.1.0 — 2026-08-10

Every entry below needs only a server restart, except Melting Pot and the six
standing Special Quests, which are derived from your own APK's BattleData and
need the event catalog regenerated first, and the drop-reference fix, which
additionally needs an APK rebuild for on-device testers — each says so in its
own text. The
earlier Attack of Coin Creeps card fix no longer needs an APK rebuild; it was
superseded before release and says so where it stands.

### Fixed

- **Chapter 30-10 settles, and a core-story clear no longer insists the wallet
  took the battle's Coins.** A tester's event log settled this one by itself.
  Every stage from 30-1 to 30-9 folds the battle's Coins into the wallet the
  client reports — 10,904 plus 936 is 11,840, and each stage before it agrees to
  the Coin — and then the Part 1 finale reports `coins: 1, exp: 1` and leaves the
  wallet at 11,840. The clear was refused for that one Coin, eight times over,
  across two force-closes, with the battle still open and every other check
  passing. What made the demand wrong is that the core story's clear Coins are
  the client's own reported figure rather than a recovered price, so the check
  was comparing two client numbers and calling the client wrong about its own
  battle. A clear may now report a wallet that folded the Coins in or one that
  did not, and settles at the balance the client actually holds, so the two
  cannot drift apart afterwards. A wallet neither reading allows is still
  refused, and still says which check refused it. The archive and Hunting clears
  are untouched: their prices are recovered, so their arithmetic stands. Server
  restart; on-device testers need a rebuilt APK.

- **A Trading Post trade spends the older Animata items once the Animata Core
  runs out.** A tester with 86 Cores and 5,796 Eggs was refused with the
  counter's own "Not enough items." while the Eggs sat on the same screen. The
  arithmetic was the server's and it was exactly wrong by design: the recovered
  rotation prices all 126 offers in Animata Core, and the trade charged that one
  item, so a purse the client counts as one total was spendable only down to its
  Core. The nine currencies and their order are recovered rather than assumed —
  `UIExchange.ExchangeItemIDs` is a static `int[9]` whose initializer blob is the
  single nine-integer permutation of the nine Animata IDs anywhere in the
  reviewed metadata, reading Core first and then the eight retired items — and
  the wiki that supplied the rotation states the spend rule three times over,
  most plainly on Animata Egg: "Unused Animata items are still usable in the
  Trading Post and will be used after Animata Core." A cost priced in any of the
  nine now draws across all of them in that order. One thing here is policy and
  is labeled as such in `trading_post_data`: that they are interchangeable one
  for one. No source states a rate, and the counter's plain sum across all nine
  is the only arithmetic the client shows for them. An operator's own catalog
  declares no pool and is still charged exactly the ingredients it names, and a
  cost the whole purse cannot cover is still refused. Server restart; on-device
  testers need a rebuilt APK.

- **A battle the server released can still be settled by the clear that
  finishes it, so a resumed battle is no longer unfinishable.** Releasing an
  open battle is right — an account must not be left unable to start anything —
  but forgetting it stranded one client path completely. A client that resumes
  an interrupted battle from its own `resumedata` posts `clear_quest` and never
  `start_quest`, so the re-entry branch that already exists to make a retried
  battle settleable is out of reach. If anything released the battle in the
  meantime — a Give Up, a declined resume, or any roster or party save the
  client writes while a results sequence is still running — every clear
  afterwards answered `story_clear_phase_conflict`, force-closing replayed the
  same clear, and no action available to the player finished the stage. The
  released core-story battle is now remembered with what its settlement reads:
  the Luck chest dealt at entry, whose Coins the client folds into the wallet it
  reports and which the wallet check therefore has to expect, the Luck growth
  rolled with it, and the Coins its Continues charged that the client never took
  off its own wallet. Starting any other battle drops the claim, and settling it
  spends it, so nothing pays twice. This grants no capability that was not
  already reachable: an account in this state could always re-enter the stage
  through `start_quest` and settle it, and this only lets the client that cannot
  send one reach the same place. This was written expecting it to be the
  Chapter 30-10 report; a tester's event log then showed that clear refused on
  the wallet with its battle still open, so this fixes a real deadlock that was
  not that one. Server restart; on-device testers need a rebuilt APK.

- **A Hunt For Joker duplicate now pays the Skill Boost the client announces,
  once, and the Luck it announces in full.** A tester reported +20% Skill Boost
  and +1 Luck where the recruit message said +10% and +10. Both figures had one
  cause each. The client raises a duplicate's Skill Boost itself and reports
  the raised value — `Character.ToHashTable` serializes `skillBoost` — so
  granting the stage's increment after the clear merged that row added it a
  second time; the grant now runs before the merge, where the server's
  increment and the client's report describe the same state and the merge keeps
  one of them. The Luck grant was 10 tenths against an announced 10.0, reduced
  earlier on a reading of the community record; the client cannot correct that
  one, because the same serializer omits `luck` entirely, so a server paying a
  tenth of the announcement contradicts the game's own message with nothing to
  tell the player which number is real. It now pays 100 tenths. Server restart;
  on-device testers need a rebuilt APK.

- **An ordinary equip or party save can no longer roll back progression the
  server had already committed.** The free-roam roster write merged the
  client's submitted members with a bare dictionary update, so a client stale
  about a character it knows overwrote that character's durable `skillBoost`
  and `jobLevels` — silently, because nothing about a save tells the player
  what it replaced. That write now runs through the same monotonic merge every
  clear already used, keeping the greater of the two values while leaving the
  members a player legitimately owns (active job, equipped slots, flags)
  client-authoritative, and keeping the members the client never serializes.
  Luck and plus count were never reachable this way, but only because
  `Character.ToHashTable` does not write them. Server restart; on-device
  testers need a rebuilt APK.

- **Lucia the Explorer II and III now honor their required keys instead of
  returning Network Error.** The reviewed BattleData declares Lucia II as 35
  stamina plus one Key of Hearts (Item 110), and Lucia III as 40 stamina plus
  one Key of Diamonds (Item 111). The generated Archive catalog discarded the
  item pair and its start handler accepted only the shorter stamina form, so
  the exact request the final client builds was refused as unsupported.

  Event generation now preserves both fields and the start transaction charges
  the declared key and stamina together, returns the resulting inventory, and
  remains one-time across duplicate requests, a lost response, clear, and
  restart. Dedicated-server users must regenerate `event-catalog.json` and
  restart the server. On-device users need a rebuilt APK because both the
  generated catalog and server code are packaged inside it. Physical-client
  confirmation is still pending.

- **Puppet Show's strict-audit ceiling now admits the observed 74-item stock
  battle.** The old aggregate of 60 was a conservative guessed policy, not a
  recovered client limit. A tester has now reported 74 items from one
  otherwise-stock battle, so the bundled `puppet_show_item_aggregate` follows
  that evidence. This setting is only used by optional `--outcome-strict`:
  exceeding it refuses the entire clear rather than discarding later chests,
  while the normal preservation path continues to trust structurally valid
  client results. No raw capture accompanied the report, and 74 is not claimed
  as the retail maximum.

- **Newly unlocked Metal, Huntland, and Arena solo stages no longer wait for
  an app restart.** The client has two independent halves of optional-stage
  visibility: selector lists in `constants` and matching `eventFlags`. Both
  its status and login callbacks can install both halves, but the server sent
  constants only with status and flags only with login. A chapter transition
  could therefore refresh one half while the other stayed at the progress
  seen during launch.

  Status and login now each return the two objects from the same account
  progress snapshot. Locked rows and their flags remain absent, and the start
  routes retain their own progress checks; this changes refresh timing, not
  unlock policy or saved progression. Server restart only.

- **Daily Quests pay the Energy their result screen promises.** A tester
  cleared Sweet Temptation, watched an Energy reward appear with no amount
  beside it, and received nothing. Both halves of that were the same absence.

  The client designates chapter 6006 its Energy quest — `EnergyGetChapter` is
  that literal in its own code — and draws the reward from a constant this
  server already advertises. But nothing in the client mints Energy; the
  retired service was expected to back that display with a real balance, and
  this server granted none. Its economy module said so in its own docstring
  and then excluded Daily Quests anyway, alongside Metal Zone and the Hunting
  zones, on the grounds that they repeat without bound.

  That reasoning does not survive contact with this one family. A Daily Quest
  can be entered once per UTC day, and only from the two the day's rotation
  names. What bounds it is the calendar, not the stage, so it is not the farm
  the rule was written to prevent.

  Every Daily Quest now pays on an accepted clear, not only the one the client
  designates — a wider policy than the client's own rule, chosen deliberately.
  The amount is the same number the constants block advertises, so the screen
  and the wallet cannot disagree. The grant is keyed by quest and UTC day
  rather than by request id, so a replayed clear cannot repeat it, and the
  balance is written to the nested wallet copy the client actually reads as
  well as to the durable one — leaving that copy stale would have shown the
  pre-reward balance on the very screen announcing the reward.

  Nothing is owed retroactively: clears settled before this landed are not
  reconstructed. Server restart, and an APK rebuild for on-device testers.

- **The dedicated server reads the recorded tool locations, like every other
  command.** `doctor` records where Java, Il2CppDumper, and the AArch64
  disassembler live so nothing has to be put on `PATH`, and every launcher
  replays that record before resolving a tool — except this one, which was
  never updated when a dedicated host gained the ability to derive its own
  catalogs.

  The symptom was two commands in the same directory contradicting each other.
  `python3 -m liminal_gate.doctor --install-missing` reported Il2CppDumper and
  the disassembler ready, both resolved from the record; a start in that same
  directory reported the master-data layout missing and told the operator to
  install Il2CppDumper, because it was looking only at `PATH`. Nothing in
  either output said which to believe, and the advice the launcher gave could
  not have helped — the tool it asked for was already installed.

  A host that keeps its tools on `PATH` was never affected, which is why this
  survived: it only appears where `doctor` did the installing.

- **The drop reference can actually be read now, on both deployments.** Two
  testers reported the same thing from opposite directions: the page was
  unreachable on a dedicated server, and one of them never had a page at all.
  Three separate causes, none of which named itself.

  The route was gated on where the server was *bound*. That answers "is this
  the operator's own device?" only inside the all-in-one package, where the
  listener is always `127.0.0.1:8002`. A dedicated host binds `0.0.0.0` — it
  has to, or no phone reaches the game — so the gate refused `/local/state`,
  `/local/events` and `/local/compendium` to everyone, the operator's own
  console included. It asks who connected now, which is what the rule was
  always about and is the stronger test: a network peer is refused whatever the
  server is bound to.

  The drop reference itself is deliberately no longer held to that rule. This
  server already serves the client on that network every resource and
  catalog-backed answer the game asks for, and the page is derived from the
  very APK those clients are running, so a tester now reads it on the phone
  they play on, at the address the client already points at. The save and the
  event log keep the loopback rule: they describe a person, and one is
  writable.

  Separately, a host whose catalogs were already current never generated the
  page. Nothing about the APK changed when the reference was added — only the
  generator did — so `catalogs_match_apk` reported them current and the
  derivation was skipped entirely. Such a host now writes the page from the
  encounter documents it already holds, without repeating minutes of
  disassembly; if those inputs are gone it says so and names
  `--rederive-catalogs` rather than silently serving a 404 forever.

  Open it with `http://`, never `https://` — this server has no certificate,
  and a browser told to negotiate TLS reports "This site can't provide a secure
  connection", which says nothing about the route. The addresses are written
  down in [what setup generates](docs/generated-files.md#reading-the-drop-compendium-in-a-browser).

  A dedicated server needs a restart. On-device testers need an APK rebuild to
  carry the gate change, though the package binds loopback and behaves the same
  either way.

### Documentation

- **The on-device event log is retrieved over `adb forward`, not `run-as`.**
  `docs/troubleshooting.md` told on-device testers to read `events.jsonl` with
  `adb shell run-as`, on the stated grounds that the self-hosted build is
  debuggable. It is not: the combined package is reassembled after Gradle
  builds it, which is why the loopback `/local/events` route exists at all —
  and that route was documented only under the dedicated server, the one
  deployment that does not need it. The fallback the same passage offered was
  wrong for a second reason: the server writes no per-request line to standard
  output on any layout, so `adb logcat` carries none of its decisions, and a
  full logcat of a failing session contains exactly one line from the server.
  Two reports arrived with large logcats and no server-side evidence before
  this was noticed. The troubleshooting table now gives the working commands
  for both shells and says plainly what a logcat can and cannot show, and the
  Network error issue form asks for the event log by those steps. Documentation
  only; no restart or rebuild.

### Added

- **The Arena menus are the ones the game shipped with, and two families come
  back with them.** A tester recorded the whole 5.5.7 menu tree as it stood at
  shutdown, and comparing it against what this server draws found two gaps that
  had nothing to do with each other.

  The first is a menu that was never served. The client has ten quest selectors
  and this server fed six of them; the missing one is Arena → Descent Quests,
  which is a different screen from Huntland → Strikes Back and reads a list of
  its own. Bahamut's, Leviathan's and Odin's Third Descents, the three Dragon
  King chapters and the Royal Rings were being advertised beside the Special
  Quests instead — playable, but in the wrong place. They are drawn in their own
  menu now. Nothing about how they start or settle changes: the menu a card
  appears in is decided by the list the server advertises it on, and by nothing
  else, and every save keeps working across the move.

  That also buys room where room was short. Arena → Special Quests cannot
  render more than thirty cards — a thirty-first hangs the client on the splash
  screen — and a finished account was already over it, so two cards were being
  withheld to keep the game launchable. Moving seven rows out leaves nothing
  withheld.

  The second gap is Battle Champs and 8-Bit Rush, nine stages that were in the
  archive all along under the wrong names. They were catalogued from their
  Japanese internal titles, which call them something else entirely, and held
  back as unrecoverable collaborations. The banner artwork the English client
  actually drew names them — Void Venom, Tempest, Dire Fang, Brushfyr, and
  8-Bit Rush — and the thing that made them "distinct and unrecovered", a
  Companion drop list no Strikes Back stage has, turned out to be sitting in
  your own APK. All five are Special Quest cards now, opening between Chapters
  19 and 23, and their tier II battles are the only place in the archive the
  Companions Samatha, Yukken, Maverick, Spike, Holy Breath, Axion Breath and
  The Ancient Key drop. A clear that claims a Companion its own stage never
  declared is refused rather than settled.

  Both need a server restart, and an APK rebuild for on-device testers, because
  the on-device package carries the same server. Neither needs a regenerated
  event catalog: an event catalog you generated before this release lands its
  Descent rows in the new menu on its own.

  What is not fixed: the *order* the Special Quest cards appear in. The record
  shows an order that is not chapter order, and this server still lists them by
  chapter. Every card the record names is now present; where each sits in the
  list is the remaining difference.

- **A dedicated server is one command again, with nothing to copy.** Setting up
  a separate always-on host used to mean running guided setup on the machine
  that builds the APK and then hand-copying four generated catalogs onto the
  server. That copy is the step operators skip, and skipping it does not look
  like a mistake: the server starts, serves the story, and then refuses an
  ordinary Companion equip with a reply the client shows as a Network Error the
  player has to force-close to escape.

  There is no copy step now. Put your own APK beside the resource tree the
  server already needs, and `server_setup` derives `character-catalog.json`,
  `companion-equipment.json`, `story-outcomes.json`, and `event-catalog.json`
  itself. The APK is read locally and nothing is sent anywhere, exactly as
  guided setup reads it.

  The first start that sees a new APK spends several minutes disassembling
  chapter programs. Each catalog records the APK it came from, so every later
  start finds them current and begins immediately; only a changed APK derives
  again. A release that corrects a *derivation* rather than the server leaves
  the APK alone and so leaves them looking current — restart once with
  `--rederive-catalogs` when a changelog entry says so.

  Deriving needs UnityPy, Il2CppDumper with a .NET runtime, and an AArch64
  disassembler; `python3 -m liminal_gate.doctor --install-missing` installs
  what is absent. A host that cannot or should not hold the APK still works:
  copy the four catalogs in as before, or pass `--no-derive-catalogs` to say so
  deliberately.

- **Startup says what this host is missing, at the end, in one block.** Every
  shortfall was already reported at the moment it happened, which is the wrong
  moment to read it — derivation and the catalog checks are minutes and
  hundreds of lines apart. A start now ends either with one line confirming the
  complete game, or with a framed block listing every missing catalog by what a
  player will actually hit ("equipping any Companion fails with a Network
  Error"), the one cause behind them, and the one command that fixes it. A
  fatal startup error is framed the same way, because under systemd it is
  otherwise followed within seconds by the whole start sequence again.

- **The chosen numbers are now yours to choose.** Some of what this server
  serves is recovered from the client; some of it this project had to pick.
  Until now the picked half was module constants, so changing any of it meant
  editing source — fine for whoever wrote it, useless to anyone running a
  release. Those values keep their defaults and gain one strict document.

  Setup writes `user-data/tuning.toml` on its first run, with every option
  documented and **commented out**, so changing a rate is an edit and a restart
  rather than a schema learned from documentation. A commented line is not
  "unset": it shows the bundled default and keeps following it, so a later
  release that corrects one of these numbers still reaches an install that
  never touched that line. Writing the values out live would have frozen them
  at install time, which is how the one corrected Pact rate and the one
  corrected roster ID in this project's history would have failed to reach
  anybody. Setup never overwrites an existing file, so a rerun cannot lose your
  edits, and deleting it means the same thing as leaving every line commented.

  Every launcher reads it from its data directory, so guided setup and the
  dedicated server need no extra option, and a systemd host changes a rate
  without reinstalling its unit. Keeping it elsewhere takes an explicit
  `--tuning`, which guided setup, `server_setup`, `bootstrap_server`, the
  systemd installer (`--tuning=PATH`), and the local configuration file all
  accept.

  It reaches the Pact rates (the "+" Pact frequency and both its gain ranges,
  the Pact of Truth class shares, per-class duplicate gains, and both pull
  costs); the Rare Companion pool's displayed class rates and the strengthen
  EXP-bonus weights; Hunting's tier and Metal Zone availability ladders and
  Puppet Show's item aggregate; the two recovered party gates; and an EXP
  multiplier. The same values
  are the defaults in `liminal_gate/tuning.py`, so a build-time edit and a
  run-time file reach the same numbers. A server launched without `--tuning`
  behaves exactly as it did.

  A partial document is the normal case: anything omitted keeps its bundled
  value, so turning off one gate does not mean restating every rate. What is
  written is validated exactly — a misspelled key is refused rather than
  silently keeping its default, because a rate that quietly does nothing looks
  the same from outside as one the server ignored.

  Three boundaries the document keeps. **Recovered values stay recovered**: the
  only ones it accepts are the two Pact costs, and only so a house-rules
  install can restate them deliberately. **It does not reach item or monster
  drop rates** — the client rolls those from its own tables and never asks, so
  no server setting can move them. And **the EXP multiplier credits, it does
  not award**: the client computes battle EXP itself, so the multiplier adds a
  further share on the server's roster, which the client reads back. It needs a
  level curve to do that, and the only source is your own
  `--clear-state-catalog`; a launch asking for a multiplier without one is
  refused rather than quietly serving the ordinary rate. Setting a multiplier
  also switches off that catalog's *experience* audit, and only that one — a
  credited roster is by construction ahead of the client's own copy, so the
  client's honest next report is lower than the sum the audit demands and would
  be refused, leaving the battle active and every later stage refused with it.
  Every other clear-state rule still applies, and the durable value is still
  protected by the merge that keeps the greater of the two.

  The two gates default to enforced, as they are today. They are switchable
  because enforcing a recovered limit is still a choice about your own archive:
  Dragon Road spent a long time serving as this game's general-purpose EXP
  route on servers that never asserted its species lock, and an operator
  restoring that deliberately is doing something different from one who never
  knew the limit was there. See
  [docs/advanced-configuration.md](docs/advanced-configuration.md).

- **"+" Pacts appear again.** Reported after 30+ pulls without one
  ([#53](https://github.com/anzensan/project-liminal-gate/issues/53)), and it
  was not luck: this server never sent the fields a "+" is made of, so the
  client had nothing to draw.

  A pull result carries a second set of gain fields beside the ordinary ones --
  `levelAdded2`, and `boostUp2` or `luckup2` -- which
  `AppServerUtil.<DoSlot>c__IteratorB` reads and the result screen renders.
  They are filled now, on a Fellowship or Truth pull as Skill Boost and on a
  Fate-type pull as Luck, the same split the duplicate gains already make. The
  gain lands on the roster as well as the screen.

  The two ranges are published and are not invented: 1 to 5 levels, and 0.5 to
  3.0 in the client's tenths. **The frequency is local policy** -- no source
  states one, both records say only "sometimes" -- and 22% is adopted from
  operator observation, sitting inside the only field estimate on record. The
  shape of the roll inside each range is uniform, which is the second and last
  thing here that was chosen rather than read. Both are named where they live
  rather than buried in the draw, and both are honest to change.

  Server restart only.

- **Six standing Special Quests that were never advertised.** Gormandizer Hunt
  (two sections, shown as Tears and Particles), The Hunt For Joker, Blade
  Falcon, Bone Killer and Ethereal, and KINO World — Chapters 3001, 3100,
  3200–3202 and 3300. Each has a nonzero BattleData battle count and each has
  its own retained banner bundles, so they are advertised from the archive the
  operator already owns and nothing is derived. Their names here are the ones
  the running client renders, which corrected two readings of the Japanese:
  `ブレイドイーグル` is Blade *Falcon*, and `インビジブル` is Ethereal.

  Every one carries an empty `dropBuddies`, so a clear settles from the
  client's own reported drops, the same way Strikes Back and Melting Pot do.
  They unlock after Chapter 3, the same permanent local gate the rest of the
  archive uses.

  Chapter 3001's third section is deliberately not advertised. It has a battle,
  but only two of its three cards were retained, and a card the archive cannot
  draw is exactly the failure the Coin Creeps fix below was about.

  **This one needs more than a server restart.** The event catalog is derived
  from your own APK's BattleData, so an existing `user-data/event-catalog.json`
  predates these chapters. Re-run the guided setup to regenerate it, then
  restart the server. No APK rebuild is needed — all six were already carded
  and catalogued on the client side; only this server had never named them.

- **Melting Pot is playable — 45 sections that were sitting in the APK
  unread.** Chapters 9100–9102 are Melting Pot: Lizardfolk, Beastfolk, and
  Human, fifteen five-battle sections each. They had been excluded because the
  client files them under a chapter range it calls "Donation", and the earlier
  reading took that label for the content. The content is not donation
  content: BattleData titles them `[るつぼの都]`, and their stamina and level
  curves match the community record quest for quest.

  The stated reason they stayed disabled has also not survived checking. Two
  client functions were cited as making the range impossible to recreate;
  both are dead in the final build. `DispDonationQuest` is a single `ret`, and
  `GetDonationQuestAmount` and `InDonationQuest` are never called at all. What
  the client does still do for these chapters helps rather than hinders: it
  hard-codes their section count at fifteen, so each race is advertised as one
  card and the client expands it, and the one request the selector makes for
  them is a route this server already answers.

  They unlock after Chapter 3, the same permanent local gate Tower and the
  Eidolon quests use, and settle from the drops the client reports — the same
  settlement Strikes Back uses.

  **This one needs more than a server restart.** The event catalog is derived
  from your own APK's BattleData, so an existing `user-data/event-catalog.json`
  predates these chapters and will not contain them. Re-run the guided setup to
  regenerate it, then restart the server. No APK rebuild is needed — nothing on
  the client side changed.

- **Candy finally has somewhere to come from.** Melting Pot is where the candy
  items live, and the reason none had ever appeared is that no enemy in the
  game drops them: of the 1,930 enemies carrying a drop table, not one names a
  candy. These chapters attach their drops a different way, written into the
  battle programs themselves — the Candy Pot carries all three Candyboxes at a
  100 ratio, and each race's six bosses carry Level, Skill, and Luck Candy at
  3. That is recovered data, not a table this project invented, which is why
  it could be turned on at all.

- **A battle's drops are the client's to report, everywhere.** Three settlement
  paths still refused rewards the client rolled, and each refusal cost more than
  it withheld: a refused clear leaves the battle active, which blocks every
  other stage until that same quest is replayed. All three now settle from the
  report.

  A stage a supplied `--story-outcome-catalog` does not name was refused
  outright, with `invalid_local_outcome`, even without `--outcome-strict`. A
  missing rule is a gap in the catalog, not evidence that the stage drops
  nothing, and the archived event chapters — the standing Special Quests among
  them — are exactly the ones no encounter map reaches. Supplying a catalog
  therefore turned ordinary play on those stages into an error. A catalog now
  constrains the stages it covers and leaves the rest exactly as they are when
  no catalog is supplied, which is what its own documentation always said it
  did. **The Hunt For Blade Falcon, Bone Killer and Ethereal each recruit their
  namesake this way**, so those three were unobtainable on any server run with a
  catalog.

  A Hunting clear reporting a Summon was refused, on the reasoning that the
  server had no authoring contract for one. `summonList` is a fixed-length
  count-per-slot array the client reports as its base plus the battle's drops,
  so it settles through the same preserving merge `itemList` already used.

  The Chapter 1100 World Map Specials refused reported Coins, items, monsters
  and Summons. They now settle, and the roster may gain a member as well as
  levels — that array is how a recruited monster reaches the account at all.
  Companions stay bounded by each battle's own recovered `dropBuddies` manifest.
  Experience keeps its ceiling, and a reported Luck roll or Skill Boost gain is
  still refused: those are not drop channels, and this server authors them
  through the Luck table and the Pact.

### Added

- **The plus-stat curves, recovered.** A character carries a *plus count*, and
  the client turns it into flat ATK/DEF/SATK/SDEF through the curve its
  `ChrInfo.plusType` names — `Entity.Status.EvaluatePlusEff` applies the result,
  so this is battle stats, not decoration.

  The table was not in the APK's asset data: `ChrDatabase.plusTypes` is a
  *private* field, so Unity never serialized it, and `GetPlusTypeParams` builds
  the fourteen entries in code on first use. They are read out of that method
  into `plus_type_data.py`, and the count matches the fourteen distinct
  `plusType` values across the client's 346 recruitable characters. Every
  minimum is 0 and every coefficient 1.0 — the constructor sets both — so the
  client's own `CalcValueAtCount` reduces to `maximum * count / 300`.

  `plusCount` is also now carried on the roster row and preserved across a
  clear. It is server-owned in one direction: `Character.LoadFromJson` reads it
  and `Character.ToHashTable` never writes it back, so every clear arrives
  without one and taking the client's row wholesale would drop it. It is kept
  the way Luck already is. The save validator bounds it at 300, because a count
  above `ActualMaxCount` does not clamp — the client logs it as tampering and
  awards nothing at all.

  **Nothing grants a plus count yet, so nothing changes in play.** The two
  channels that did — a Pact result's `plusup` and a Rebirth's
  `addedPlusCount` — were server-owned rules the retired service kept to
  itself, and no recovered source gives their size. This describes what a count
  is worth; it does not invent one.

### Fixed

- **One bad field in the Companion box closed all of Huntland.** Every Hunting
  clear validated the account's Companion box — each row's inventory id, their
  uniqueness, and `nextCompanionInventoryId` — before it looked at what the
  battle had actually dropped. That list is usually empty, and the item and Coin
  families can never drop a Companion at all, so a box that had drifted out of
  step refused clears on quests whose battles never touched it. The reward
  screen then retried a settlement that could never complete, which is the
  Network Error a player has to force-close.

  It presents as Huntland breaking all at once, permanently, while the main
  story keeps working: the story clear never consults the box, and the box lives
  in durable server state, so an app restart, an APK rebuild and a reinstall all
  leave it exactly as it was.

  The box is now consulted only by a clear that actually delivers a Companion,
  matching the response contract beside it and the World Map Special clear's own
  guard. A drop the stage cannot author, or a box with no room for one, is still
  refused wherever a Companion is really granted.

  If you are stuck on this now, `python3 -m liminal_gate.account_state validate`
  names the field; see `docs/saves.md`.

  Needs a server restart, or an APK rebuild for the on-device package.

- **A refused Hunting clear said only that something was wrong.** Eight distinct
  causes answered two error names, and `tutorial_state_conflict` is returned by
  thirteen other call sites besides. A stale Companion box, a wallet
  disagreement and a battle fought on the wrong map were indistinguishable in a
  dump, which is why the entry above took a source reading rather than a log to
  find.

  Each check now names itself, exactly as the core-story and archive clears
  already did: `hunting_clear_stage_conflict`, `_phase_`, `_active_stage_`,
  `_progress_`, `_world_map_` and `_wallet_conflict`, and the settlement half
  splits into `invalid_local_hunting_bounds`, `invalid_local_hunting_items` and
  `invalid_local_hunting_companions`. Every status is unchanged; only the name
  is sharper.

  Needs a server restart, or an APK rebuild for the on-device package.

- **A day-one login bonus could not be opened.** Reported by two testers on
  fresh installs (Issue 54): the inbox lists "Login bonus day 1" and
  "Consecutive login bonus day 1", and opening either answers a Network Error
  the player has to force-close to escape. The dump named
  `unsupported_message_read` on `/gd/read_messages`, and the mail route turned
  out to be the wrong place to look.

  The scripted tutorial's five clear callbacks each carry the client's own
  181-slot inventory. Each one validated that array and then stored none of it:
  no transition named `itemList` among the fields it kept. A player therefore
  reached free roam with no inventory recorded at all — and every route that
  settles a reward into that array checks it before doing anything. The read
  refused a bonus of pure Coins and Energy over the shape of an inventory it was
  never going to touch, and said so in the vocabulary of the mail route.

  The tutorial now keeps the two count arrays it was already accepting, merged
  the way every later clear merges them, so a client reporting a stale base
  cannot erase a count granted between its read and its clear. A save already
  stranded past the tutorial gains a zeroed inventory when the server loads it;
  one that already carries counts is left exactly as it is, whatever its length,
  because the per-route slot checks own that judgement.

  This is also the answer to the second report, that the problem fixed itself
  overnight. It was not the server settling in: clearing any Chapter 2 quest
  wrote the missing array as a side effect, because the ordinary story clear
  always kept what the tutorial discarded. The waiting bonuses were never lost —
  inbox presents do not expire — and open normally now.

  Needs a server restart, or an APK rebuild for the on-device package.

- **Tower of Temptation said you did not meet the requirements.** Reported by
  two testers: all four cards list, and tapping any of them answers "You don't
  meet the requirements to unlock this quest. Check the event notice for
  details." Nothing appears in the server log, because nothing was ever asked of
  the server — the client refuses on the device.

  The client sorts quests by chapter number, and the ranges are fixed in the
  app. Chapters 9000–9009 are its **Raid** quests; Tower of Temptation is
  9010–9099. This server serves Tower of Temptation from 9000–9003, because
  those are the copies that carry the artwork and the compiled battles, so every
  Tower card takes the raid path — and a raid quest asks for a status block the
  server had never sent. Missing, that block reads as "locked", which is the
  message word for word.

  The login reply now carries that block for any advertised quest in the raid
  range, marking it open with a full boss health bar. No end date is sent with
  it: that is what would draw a countdown, and the schedules the original
  service ran were never recovered. The cards look exactly as they did; they
  open now.

  Verified on the reviewed client: Tower of Temptation Alika opens its team
  screen at 15 stamina. Its clear has not been played.

- **The "To another world" menu opened onto a Network Error.** The previous
  entry made both rows appear. Choosing one still failed, and so would every
  battle behind it — reported by a tester the same day, on a save that showed
  the server had never recorded the step onto the map.

  The client sends the map you are standing on and the progress you have made
  *on that map* in the same field it uses for your main story position. On the
  main map that field is your story progress; the moment you step onto a side
  map it becomes that scenario's own progress instead. This server read it as
  the story position either way, so it refused the step onto the map, refused
  the flush the client sends after each side-scenario battle, and would have
  refused the battles themselves.

  All three are now answered against the map they name. Stepping onto BreaSoul
  or the Five Emperors works, their battles settle, and clearing a section opens
  the next one. What the client reports about its own position is still not
  taken on its word: a scenario cursor naming a section that scenario does not
  have is refused, and progress you have not played is not credited from it.

  Your main story position remains untouched by any of it. Needs only a server
  restart — on-device testers pick it up by rebuilding, as they do for any
  server change. Still unplayed: this was read out of the client, not watched
  on the wire.

- **The two side scenarios could not be entered, and the menu that reaches them
  could not appear.** BreaSoul and the Five Emperors — the "To another world"
  scenarios, thirty stages between them — were served but unreachable. Two
  separate things were missing, and either one alone was enough.

  The menu is drawn behind the client's own check that you have reached
  Chapter 26 (BreaSoul) or Chapter 20 (the Five Emperors), and it reads that
  progress out of a per-world field this server had never sent. Absent, the
  field reads as zero, so both entries stayed hidden no matter how far you had
  played. And once you did stand on one of those maps, the client tells the
  server which world you are on — a value this server compared against on every
  clear and never wrote. Walking onto a side map therefore failed twice: the
  step onto it was refused, and every battle behind it was refused after that.

  Both are now sent and accepted, and a side-scenario clear opens the next
  section of its own world. Your main story position is untouched by all of it,
  which is deliberate: the two scenarios keep their own progress, so playing
  them cannot move your world map or your stamina ceiling.

  Enabled with the same `--secondary-worlds` the scenarios already used, and it
  needs only a server restart — on-device testers pick it up by rebuilding,
  as they do for any server change. None of this has been played yet: the
  thirty stages have never run against this server, and the client contracts
  behind them were read out of the client rather than watched on the wire.

- **Strikes Back only ever offered its first stage.** Every family you had
  unlocked showed one card, and the card was one battle. It read like the
  higher tiers were waiting on later progress. They were not: they were
  unreachable, and no amount of progress would have reached them.

  A Strikes Back card is a folded card — the client expands it into its tiers
  itself. But it decides whether a row folds by looking at the row's name: a
  name carrying a section, like `8000-1`, is one stage, and a name that is just
  the chapter, `8000`, is a card. This server sent the first form, so every
  family was drawn as a single stage and tapping it started tier 1 directly.
  The server now sends the chapter, and login names each tier the card
  contains individually rather than naming the chapter once.

  That last part matters more than it sounds. The client asks every Strikes
  Back card for five tiers, but Chapters 8012–8017 only have three. Naming the
  chapter once would have offered all five, and the two that do not exist have
  no stamina, no battles, and no way to start. Naming the tiers individually
  offers exactly the ones that are there.

  Tiers 2 and up were always accepted by the server; nothing about their
  stamina, rewards, or the Chapter 5–18 unlocks changed.

- **Pressing a Pact you cannot afford left the game in an error state.** The
  client does not gate that button locally, so pressing it while short is an
  ordinary thing to do, and its pull callback reads `coins` and `energy` off
  the response *before* it branches on the refusal code. The refusal carried
  neither, so the client read keys that were not there.

  Every Pact refusal now carries the wallet -- short of Coins, short of Energy,
  short of a ticket, or a pool with nobody left in it. Nothing is charged and
  nothing is drawn, exactly as before; the difference is that the client can
  read the answer and show its own message.

- **A map reveal the account had already applied was refused, with no way
  out.** The client announces the world map after a chapter boundary. If the
  server had already applied that reveal, the announcement was answered with a
  conflict -- and a conflict reaches the client as a transport failure, so it
  raised a dialog, re-announced the same map on the next open, and was refused
  identically. Nothing the player could do would clear it.

  A reveal that names exactly the progress and world map the server already
  holds is now answered as the settled no-op it is. Progress does not move and
  nothing is written. A reveal naming anything else is still refused.

- **A refused request could not be read from its own diagnostics.** Two reports
  of a 501 arrived this week that the log could not tell apart. A refused
  `start_quest` withheld the entry costs the client declared, so an unknown
  stage and a cost disagreeing with the catalog produced identical lines; a
  refused mail read withheld everything about `idlist`, so a malformed form and
  an unknown message did too.

  The declared entry costs (`stamina`, `coins`, `itemID`, `itemCount`,
  `helpItemID`) are now recorded. They are stage economics -- the very values
  the catalog is compared against -- not account state. For the mail routes the
  log records whether `idlist` parsed and how many entries of what type it
  named, and never the IDs themselves.

  This changes no behaviour. It exists so the next report of either shape
  answers its own question.

- **A recode reported no gain, and carried less than it should have.** Two
  halves of the same gap, found while reading the client's recode callback: it
  reads `overlapped`, `addedSkillBoost`, `addedLuck` and `addedPlusCount`, and
  this server sent only the first, so the result screen showed nothing however
  much the recode carried. All four are sent now.

  The carryover itself was also short. A fifth of each material monster's Skill
  Boost comes across on top of the source's own -- a monster at 100% contributes
  20%, the pair at most 40% -- and an already-owned destination takes 5 Luck.
  Neither was applied. An owned destination also *gains* the carryover rather
  than being overwritten by it, and keeps its level, which is the same record's
  rule and the reason the fix above it stands.

  This is documented community record rather than recovered structure -- the
  retired service owned the arithmetic and the client holds no table for it --
  so it is labeled as such beside the two constants, the same way the Pact
  class shares are. Mistwalker's own play guide covers the requirements and
  warnings but not the proportions.

  Server restart only.

- **Recoding into a character you already owned destroyed the copy you had.**
  The rebirthed unit replaced the held row outright, so a developed copy of the
  destination lost everything: a level 90 unit with 95.0 Skill Boost and 80.0
  Luck came back at level 1 with zero of both, and no route exists to recover
  any of it.

  The two rows are now merged on the rule the clear settlement already applies
  to a stale client -- job progression, Skill Boost, Luck and plus count only
  ever accumulate, so the larger of the two values is the true one. The
  rebirthed unit still starts at level 1 and still carries the source's Skill
  Boost and Luck; what changed is that a held copy further along in any of them
  keeps what it had.

  Server restart only. A save already flattened by an earlier recode cannot be
  repaired from here: the values it held were never written down.

- **Dragon Road and Machine Road let any party in.** Raised right after the
  Captive Golem fix below, as a suspected second case of it. It is the same
  defect — a limit the game declares and nothing enforces — but a different
  field, so that fix did not reach it.

  The Roads do not declare a class band. They declare a *species* lock, and
  they are the only two sections in the entire game that declare one: 1200-1
  admits Dragons, 1201-1 admits Machines, which is what their names have always
  said. The client has a refusal for it, right beside the class one, but the
  gate that would raise either never looks at your party — so both were the
  server's to enforce, and it enforced neither.

  A party that breaks the lock is now turned away before anything is charged,
  with the game's own message rather than a Network Error. One wrong member is
  enough, which is the limit as declared. A character the local tables cannot
  describe is not refused.

  **This is a visible change to how the Roads have been playable.** Dragon Road
  in particular has been usable as a general-purpose EXP route for any party;
  it was only ever open to that because nothing asserted the limit. Nothing
  about either Road's rewards, stamina cost, or unlock changed. Server restart;
  no APK rebuild and no catalog regeneration — an operator's own hunting
  catalog picks the limit up from the recovered table by stage identity.

- **Captive Golem let any class in.** Reported after walking a class-8
  character into the quest to see whether it would be stopped. It was not.

  Chapter 2008's four sections declare `classMin`/`classMax` of 1-6, 1-5, 1-4
  and 1-3 — a descending ladder that *is* the quest. They are the only sections
  in the game that declare a class band at all; every section of all forty-two
  story chapters, both Huntland ranges and every other event archive was
  re-read from the reviewed APK to be sure of that.

  Nobody enforced it. This server never carried the fields. The client owns
  `StartQuestErrorCode.ClassLimit`, but the gate that returns it —
  `AppServerUtil.IsEnableToStartQuestLocal` — reads only stamina, Coins, items
  and VS stamina and makes no class-related call, so it cannot produce that
  code. The limit was declared by the game and asserted by nothing.

  The four bands are now carried, and a start whose party breaks one is refused
  under the client's own `ClassLimit` code in the soft shape the Daily Quest
  rotation already uses, so the player sees the game's refusal rather than a
  Network Error. A character the local character catalog cannot describe is not
  refused: this restores a declared limit, it does not invent one for state it
  cannot read.

  Server restart only, and no catalog regeneration: the bands are applied from
  the recovered table when a catalog loads, so an `event-catalog.json` built
  before this still gets them.

- **Using a candy item, or claiming an achievement, hung the client on
  "Connecting".** Reported straight after the candy fix below: the item could
  finally be used, and confirming it left the loading screen up forever.
  Restarting showed the use had gone through — item spent, Luck gained — so
  the server had settled and answered it before the client stopped.

  The client's transport reads one field of every reply without checking
  whether it is there: the flag that says whether the request succeeded. Two
  routes had never sent it. Missing, it does not read as a failure — it throws,
  inside the transport itself, after the change is already saved. The screen
  that was waiting is never told anything, so the overlay it raised stays up
  and nothing short of a restart clears it.

  Neither route had ever been reached by a real client before: candy was
  unusable until the fix below, and no tester had claimed an achievement. The
  flag is now stamped on every reply that does not carry a verdict of its own,
  in one place, so no route can leave it off again. An endpoint's own refusal
  code still rides the field it always did.

  Server restart. Anything settled before a hang stays settled.

- **A full Companion box turned a won Metal Zone battle into a Network Error
  loop.** Reported against All Hail The King 30-39
  ([#58](https://github.com/anzensan/project-liminal-gate/issues/58)): the
  screen after the Metal Minions dropped looped Network Errors until a
  force-close.

  A drop with nowhere to go was treated as an invalid battle result. It is not
  one — it is an ordinary game condition, and the client has no way to avoid it
  or to say so: `StartQuestErrorCode` names stamina, Coins, items, class,
  species and progress, and nothing about the Companion box, so the client
  enters, wins, and reports the drop into a box it knows is full. The refusal
  reached it as an unsigned 409, which reads as a transport failure rather than
  an endpoint answer, and a refusal leaves the battle open, so every retry was
  refused identically. Only selling Companions escaped it.

  The battle now settles and the box keeps as many of the drops as it holds.
  The overflow is dropped rather than granted past `maxBuddyBoxCount`, because
  a box longer than the ceiling the client is told about is a shape its own
  screens were never given. A drop the stage cannot author is still refused,
  wherever it appears in the reported list — a full box does not turn an
  undeclared Companion into an accepted one. Story stages settled Companion
  drops through the same rule and had the same defect; both are fixed.

  This one needs only a server restart. The stage's own drop manifests were not
  the problem and are unchanged: Chapter 3000's `dropBuddies` were re-read from
  the reviewed APK for all fourteen playable sections, and All Hail the King
  declares exactly what the regular zones do.

- **A big enough haul ended in a Network Error loop at the item screen.**
  Reported against Puppet Show Lv. 20-39 with 47 item chests
  ([#57](https://github.com/anzensan/project-liminal-gate/issues/57), on-device
  on a Pixel 7 Pro): the post-battle item screen showed Network Error over and
  over and only a force-close escaped it.

  This server told the client one inventory ceiling and enforced another. The
  constants block sends `maxItemCount` 9999, which is what the client then
  allows a slot to hold; every server-side item projection was written against
  999, a figure that entered as a save-editor invariant and was never checked
  against the client. A clear whose drops carried any slot past 999 therefore
  reported an inventory this server called impossible, and refused it with
  `invalid_local_hunting_result` — an unsigned 409, which the client reads as a
  transport failure rather than an endpoint refusal, so it showed the network
  dialog and retried. The refusal also leaves the battle open, so every retry
  was refused identically, exactly as in the Counter Descent defect below.

  Nothing needed to be unusual about the run except its size: 47 chests is
  roughly the width of the gap, so it was the players deepest into farming the
  species materials who hit it first. The one ceiling is now the client's own,
  named once and sent from the same constant it is enforced against, so the two
  cannot drift apart again. The lower figure was also refusing valid saves in
  the editor's validator and truncating mailed, achievement, and Trading Post
  item grants at 999; all of those now reach the ceiling the client honours.

  **Hunting, Metal Zone, Daily Quests, and events need only a server restart.**
  A `user-data/story-outcomes.json` generated before this fix carries the old
  999 in its own capacities block, so story-stage clears keep refusing until it
  is regenerated — re-run the guided setup, then restart.

- **Metal Minion evolutions ate one Companion too many.** A tester reported the
  two Metal Minion recipes costing eleven and four copies where the client's own
  numbers are ten and three.

  The recovered recipes carry a copy count instead of item costs, and that count
  is the whole Companion cost — the one being evolved is the first of the ten,
  not a twelfth Companion on top of them. This server had read it as duplicates
  owed *besides* the base, so every Metal Minion evolution consumed one extra
  and a player holding exactly the ten the client asked for was refused
  outright. Both recipes now settle at their recovered cost. Server restart;
  the recovered values themselves are unchanged.

- **Candy items said no character could take them.** A tester with a Luck
  Candybox from Melting Pot's Candy Pot opened the item and was told it could
  not be used on anybody. Every candy item behaved the same way, and no error
  explained it.

  The client filters that character list on one lookup: a table of item
  effects the *server* sends with everything else in the status block, which
  this server had never sent. With the key missing the client builds an empty
  table, every item misses it, and every character is filtered out. The effects
  themselves were already recovered and this server has always been able to
  spend candy — only the client's own gate was absent, so it was refusing a use
  the server would have settled.

  The table is now sent, derived from the same policy the server applies, and
  only while that policy is loaded — so the client offers exactly the items a
  use would settle. Server restart; nothing on the client side changed.

- **Chained event sections never opened, however many times you cleared the
  one before.** Melting Pot stayed one section long per race, and Tower of
  Temptation the same.

  Those sections are unlocked by the client, not by this server: each one names
  the section before it, and the client hides it until the account's own record
  of cleared quests contains that parent with a date. This server had never
  kept such a record — nothing in the save knew which individual stages had
  been cleared — so the second section of every chained chapter was not greyed
  out, it was never in the list.

  Every clear the server settles — story, Archive events, Hunting, and the
  Chapter 1100 Roads — now stamps the stage it cleared and hands the client the
  updated record in the same response, so the next section appears without a
  trip back to the title screen.

  **Clears from before this change were not recorded and cannot be recovered.**
  If Melting Pot Lizardfolk 1 was already cleared, clear it once more and
  section 2 appears. Server restart; no APK rebuild.

- **Attack of the Coin Creeps and Tower of Temptation were being served from
  the copy of themselves that has no artwork.** BattleData carries both
  families twice. Chapters 1003 and 3002 hold the same three `マネマネ参上`
  sections at the same 10/15/20 stamina and the same assumed levels; Chapters
  9010–9013 and 9000–9003 hold the same four `[誘いの塔]` bosses across three
  sections at 15 stamina, chained by the same `parentQuest` links. The two
  copies are not variants. They are the same stages under a second chapter
  number.

  Only one copy of each pair was ever card-backed. The client's own
  `AssetVersions` catalog has records for `sp3002-1`–`-3` and for
  `sp9000`–`sp9003`, and **none at all** for `sp1003-*` or `sp9010-*`. This
  server had picked the un-carded copy both times, which is why the Coin Creeps
  cards had to be derived from one retained family bundle in the first place —
  the artwork was never missing, it was filed under 3002. Tower had been
  advertising four cards the archive cannot draw.

  Both families now come from the copy the original archive shipped cards for.
  Verified against the reviewed client: all four Tower cards render, Attack of
  the Coin Creeps renders, and its `start_quest` settles. The separate Coin
  Creeps card derivation is left in place but is no longer reached.

  Coin Creeps needs only a server restart — its stages are declared in the
  bundled Hunting policy. Tower is carried by the event catalog, which is
  derived from your own APK, so an existing `user-data/event-catalog.json`
  still names 9010–9013: regenerate it with the guided setup, then restart. No
  APK rebuild either way, because the client already carries every catalog
  record involved.

- **A save that failed to write could still be reported as saved.** Every
  mutation changes the account in memory and records the answer it will give to
  a retry, then publishes the whole save. If that publish failed, both of those
  survived in memory — so the request that failed came back as a dropped
  connection, and the *retry* was answered from that record with a cheerful
  success for a change the disk never took. It looked saved until the next
  restart, when it was simply gone.

  Publishing writes the entire save at once, so a failure means nothing landed
  and the file still holds the last state that did. It is now re-read on that
  path, which undoes the change and the recorded answer together. A retry then
  does the work again for real and reaches the disk. Nothing about a successful
  write changed.

- **"The save survived the update" was not checking whether the save
  survived.** The on-device update compared which accounts existed, and the
  import compared which account was active. Neither looked inside them, so an
  update that kept your account and emptied it — progress back to zero, coins
  gone — printed the reassurance anyway, before even the account check ran.
  Both now compare the progress itself and name what moved, and the message is
  printed only once that comparison passes. The stamina meter's fill origin and
  the timestamp the server rewrites are excluded, since those move on their own,
  and whole numbers that come back as decimals are not treated as changes.

- **A resource file replaced while the server ran was served as though it were
  the original.** Files are hash-checked when the manifest loads and were then
  reopened by path for every request, so anything that changed afterwards went
  out under the manifest's identity. If the replacement was a different length
  it was worse than wrong: the response still advertised the manifest's length,
  leaving the client reading a body that could not match it, which reads as a
  transport failure rather than as the stale manifest it is. Each file is now
  measured and digested again as it is opened, before the response is framed,
  and a changed one is refused with an error that says so. Putting the original
  back serves it again.

- **The pre-battle Power-Up Item slot is back.** A tester reported that the
  row above Start Battle — the one that let you spend a Disarmer or an EXP
  Boost on the run you were about to start — never appeared, and wondered
  whether it was progress-locked. It was not locked; the server was never
  turning it on. The client gates that row on a single server constant.
  `UITeamPopup` caches `IsHelpItemEnabled()` while it builds the screen, and
  that predicate returns false unless `UserData.helpItemEnabled` is true.
  Nothing about the account is consulted, which is why a player holding
  Disarmers saw the same empty screen as one holding none. The constants block
  had never carried the key, so it defaulted to false for every account since
  the server was written.

  Sending the flag alone would have made things worse. When a power-up is
  chosen, the client adds a `helpItemID` field to the start body — and only
  then; it omits the field rather than sending zero, which is why the shorter
  form is the only one ever seen so far. Under strict parsing the longer form
  would have failed to parse and refused the battle outright, so choosing a
  power-up would have broken starting the quest. Both start forms now accept
  the field in the one position the client emits it, the ordinary one and the
  Metal Zone ticket one.

  The spend is the server's. The client only paints the slot — it never
  decrements the count — and it replaces its whole inventory from the start
  response, so the chosen item is debited here and the new inventory is
  returned with the start. All eight of the client's own HelpItem-kind items
  are accepted: Time Extension, Disarmer, EXP Boost, Coin Boost, and the four
  Reinforcements. An ordinary start without a power-up is unchanged and still
  reports no inventory at all.

  Two things worth knowing while using it. Candy items and the four
  Reinforcements have no local source yet — the only places they ever came
  from were Tower of Temptation milestones, Melting Pot Lizardfolk, and
  Ultimate Five, and those rewards were authored by the retired service rather
  than by the client, so they exist nowhere in the APK to recover. The four
  boosts do drop: Crystal Road, Crystal Roundelay, and the Trading Post all
  pay them. And the slot stays hidden during the tutorial and on World-0 map
  specials, which is the client's own rule, not a local one.

- **Companion pulls now follow the rates the game displayed.** A tester
  reported 12 Companion Ticket pulls coming back 5 Z, 4 S, 2 A, 1 B, and
  suspected the tickets. The tickets were fine — they pay for the same pool the
  Energy press draws from, and payment never touched selection. The pool did
  not weight its members at all. Every one of the 114 rare-slot Companions was
  equally likely, so what came out reflected who was *in* the pool rather than
  the odds the service advertised, and the pool leans the opposite way from its
  own rates: half its members are S and only two are B. That returned Z at
  16.7% against a displayed 3%, and B at 1.8% against a displayed 49% —
  the two commonest results, inverted. Twelve pulls were enough to see it: that
  spread is about 54,000 times more likely under the flat pool than under the
  real table.

  The rates were known but unusable, because the bundle had no record of which
  Companion belonged to which class. `BuddyData.rarity` has carried it all
  along, on the same master object the pool membership and the Companion sale
  and evolution tables already come from. The 114 are now grouped by it and
  each class draws its displayed share: Z 3%, SS 8%, S 10%, A 30%, B 49%. The
  grouping agrees with the community record exactly — 19 Z, 13 SS, 50 S, 30 A,
  2 B — so the two records corroborate each other rather than one being taken
  on trust. Within a class the split stays even, which is as far as the record
  goes. The Coin pool is unchanged and still uniform; nothing was found that
  describes its rates, and its two classes are near-evenly sized anyway.

- **Attack of Coin Creeps cards no longer blank out at random.** Two testers
  reported the same shape from different directions: one card empty after
  playing an unrelated quest, another missing and then "strangely" back later.
  The artwork was never absent. All three Chapter 1003 cards are derived from
  one retained Coin Creeps-family bundle, and the derivation renamed the
  texture, the container path, and the bundle — but not the serialized file
  inside it, which all three inherited from the source. Unity keys a loaded
  bundle by that internal file and refuses to load one another loaded bundle
  already provides, so whenever two of the cards overlapped, the second load
  returned nothing and the card drew empty. The client unloads each bundle on a
  delay after reading its texture, which is why the same card could be blank
  once and fine the next time. Decoding 1,200 retained bundles found no
  duplicate internal name anywhere: uniqueness was an invariant of the original
  archive that only the derivation broke. Each derived card now carries its own.

  **This one needs an APK rebuild and regenerated derived files, not just a
  server restart.** The client stores downloaded artwork as `<asset>_<ver>.bin`
  and reuses it without asking again, so an install that already cached the
  broken cards would keep them no matter what the server serves. The three
  aliased catalog records now carry their own asset version, which is what makes
  the client discard the stale copies and fetch the corrected ones. Rerun the
  complete setup command, which rederives the three bundles, and reinstall the
  newly signed APK. Your save is untouched: it lives on the server, not in the
  client.

  **Superseded before release by the Chapter 3002 move above.** The reason the
  three cards had to be derived at all was that Chapter 1003 has no retained
  artwork; Chapter 3002 is the same three sections and has all three cards. The
  server now serves 3002, so nothing requests `sp1003-*` and neither the
  derivation nor the APK rebuild described here is required. This entry is kept
  because it is where the Unity internal-name invariant is written down.

- **Tickets of Fellowship work in batches, and work on Companions at all.**
  Two separate refusals wore the same face: an unsigned 501, which the client
  can only read as Network Error.

  On the character page, the ticket form was accepted for exactly one result.
  That came from a single capture of a one-ticket press, and it was the wrong
  generalization: `UIBarSlot` wires its ten-pull control to the ticket variant
  as well, and sizes that batch from the ticket count the player is holding, so
  anyone with more than one ticket who used the bulk button posted a `count`
  the server rejected. Tickets now settle in the same one-through-ten batches
  every other Pact form allows, one ticket per result, refused whole rather
  than part-paid when the batch outruns the tickets left.

  On the Companion page nothing worked, because the server knew only half of
  that screen. The Companion draw has two pools, and the server implemented
  one: the Energy-priced rare pull and its Companion Ticket. The Coin-priced
  pull -- the one the Fellowship Ticket pays for, drawing from a different and
  disjoint 81-Companion pool -- was never a supported wire kind, so every press
  of it failed, ticket or Coins, one or ten. Both pools are now served, each
  spending its own ticket ahead of its own currency, and a shortfall answers
  with that pool's own error code instead of a dead route.

  The Coin pool is bundled policy under `--companion-draw` (a standard flag),
  where its 81 members are recovered client data and its uniform selection is
  local policy, the same split the rare pool already documents. A
  user-supplied `--companion-draw-catalog` has no schema for a second pool, so
  under one the Coin pull stays unsupported rather than quietly drawing from
  the rare pool.

- **A Luck Treasure Chest could show a Companion and give you nothing.** Chests
  award four kinds of reward. Coins and items were settled from the start; the
  other two were computed and then dropped on the floor. `chest_companions()`
  existed, was unit-tested, and had no caller anywhere in the server, while the
  chest pools carried thirty-nine Companion rewards across twenty-seven stage
  and tier slots. A clear returned 200, the items and Coins landed, and the
  Companion was simply gone. Nothing in the suite looked at an authored chest
  end to end, which is how it shipped.

  The asymmetry is structural rather than a slip. The generic story clear body
  is an exact field tuple — `chrdata`, `itemList`, `summonList` and no Companion
  box — so there is no field for the client to report a chest Companion back
  through, and no amount of reconciliation could have caught it. Coins and items
  work because the client folds those into the balances it submits. The server
  authored the chest at battle start and persists it in `active_luck_result`, so
  it now grants what it authored, inside the clear's own transaction: an exact
  replay returns the cached payload and cannot grant twice, and the grant
  survives a restart.

- **One Pact of Fellowship slot was a character that does not exist.** The
  bundled roster listed ID 122, which names nothing in the client's own decoded
  name table and appears in no character catalog, while 126 — Megacell — was
  missing entirely. Megacell was unobtainable from the Pact, and roughly one
  pull in 103 handed back a character the client has no data for.

  A count check could never have caught it: 103 IDs listed, 103 expected. It
  surfaced by resolving the community record's *names* into IDs and then
  checking each one's recovered class against the class the record printed. All
  103 now agree, which corroborates the roster rather than merely transcribing
  it. The neighbouring entries are 123, 124 and 128 against a documented cluster
  of Regenercell, Mechavirus 3721, Megacell and Wastecell, so 122 was a slip of
  the pen for 126.

  A Pact-enabled server now refuses to start if any pool member fails to resolve
  in your own character catalog, rather than waiting for someone to draw it.

### Added

- **Chests now appear across the whole game, not only the thirty documented
  stages.** The community record covers thirty story stages, so a player at
  Chapter 10 with real Luck never saw a chest — nobody wrote that page. A stage
  the record does not document is now answered with the pools it *does* document
  for the two chapters that stage sits between, merged and deduplicated. On by
  default; `--no-interpolated-luck-pools` restores the record-only behaviour.

  **No reward is invented.** Every Coin amount, item, Companion and character a
  chest can produce this way already appears in the record, for a chapter
  adjacent to the one being played — asserted directly by a test. What is chosen
  is *placement*: that Chapter 10, which nobody documented, pays what Chapters 9
  and 13 pay. No Coin curve is fitted and nothing is scaled, because the
  record's own Coin values do not sit on a clean curve — Chapter 1 pays 50 where
  the trend through 4 to 36 would predict far more — and fitting one would
  replace sourced values with derived ones.

  Both bracketing chapters rather than the nearer one, because single-chapter
  coverage is often a stub: Chapter 9's only documented stage carries one item
  in A and one in B, and donating that alone would make most of the game poorer
  than the record actually describes.

  **The thirty sourced stages are never touched**, and a stage the record names
  while leaving a tier empty keeps that tier empty — that is the record
  speaking, not a gap. So what came from the record stays distinguishable from
  what this project arranged, and the server says which mode it is running in on
  every start. `PARITY_ROADMAP.md` still classifies the real rates and pools as
  unrecoverable, because arranging the record's contents does not recover the
  retired service's table.

- **`--luck-pool-catalog`: your own chest pools, for the stages the record does
  not cover.** The bundled table documents thirty story stages and every other
  stage rolls six empty slots, which is honest but leaves a real feature nearly
  inert for most of the game. This is the deliberate way past it: an operator
  supplies pools in a strict user-local catalog, the bundled table stays exactly
  as sourced, and the running server names the loaded file in its startup output
  so invented contents never quietly read as recovered ones.

  It is a file and not a default on purpose. Everywhere else this project sets
  local policy it sets a *bound* or a *gate*, and those fail safely — a reward
  ceiling that is too generous only ever declines to refuse an honest claim. A
  chest pool is generative, so no direction of being wrong is harmless, and
  nothing could ever catch it: the server authors the chest and the client
  renders whatever it is told, holding no table of its own to disagree with. A
  save that collected from an invented pool cannot afterwards be told apart from
  one that did not.

  A stage the catalog names replaces the bundled pool for that stage outright
  rather than merging, so no pool ends up sourced in part and invented in part.
  Rewards use the client's four wire forms, and the loader refuses an unknown
  tier, a malformed reward, a zero identifier, a duplicate stage, and a repeated
  reward — a repeat inside an equal-weight tier is a weight by another name,
  which is the thing the record does not carry.

- **Sixty-five character rewards recovered into the Luck chest pools.** The
  scrape behind those pools dropped ninety-nine rewards it could not resolve,
  sixty-eight of them character icons, and character rewards were consequently
  absent from every pool even though the record shows chests award them. The
  icons kept their names, so sixty-five resolve by exact match against the
  operator's own `ChrDatabase` and are now emitted in the client's `M` wire
  form. Nineteen of the thirty pooled stages still lose at least one reward,
  down from twenty-eight.

  Three do not resolve, and it is a real ambiguity rather than a lookup failure:
  the wiki writes `Mage (Ice)` and `Lizardfolk Mage (Fire)` while the master
  data holds four characters named `Mage` and four named `Lizardfolk Mage`,
  separated by an element the catalog does not name. Choosing one would be a
  guess, so they stay unresolved and are named in the module.

  Recorded and deliberately not acted on: the four rewards the scrape filed as
  unresolvable *item* names are not items. Three name characters the master data
  holds, and the fourth, `Metal Minion`, is Companion 128 — already used by
  these pools elsewhere. All four look like a wiki editor reaching for
  `{{Item icon}}` where the reward was not an item. Correcting a source is a
  different decision from reading it, and is left to be made deliberately.

  Adding rewards to a tier changes which one a given seed selects from that
  tier. Nothing durable depends on a seed-to-reward mapping, and the per-tier
  draw already isolates neighbouring tiers, so this affects only which reward a
  future chest rolls.


- **A Companion delivered by an inbox present was owned but invisible.** A
  reporter opened the Companions screen after a present granted one, saw
  nothing, restarted the app, still saw nothing, then drew a Companion and
  immediately held two. Nothing was lost at any point — the present's Companion
  had been granted and persisted correctly the whole time.

  `buddyInfo` carries two halves: `list`, the Companions owned, and `record`,
  the book with one entry per distinct Companion. `record` is a projection of
  `list`, not a second store, and every grant path rebuilds both together
  through `_companion_info` — a battle drop, a draw, a Trading Post exchange, a
  sale, a strengthen, an evolution. The inbox present was the one exception: it
  appended to `list` and left `record` untouched. The box the client renders
  therefore never learned about the Companion, and a restart could not help,
  because the save itself was inconsistent rather than the client's copy being
  stale. Any later mutation rebuilt the box wholesale and the missing Companion
  reappeared alongside whatever had just been added, which is the "pulled once,
  now I have two" the report describes.

  The present now rebuilds both halves like everything else, and a save that
  already drifted is repaired when it loads — the owned list is the truth, so
  the book is rebuilt from it and nothing is granted or taken. That is the same
  treatment the stale wallet projection got in 1.0.4, and for the same reason:
  a projection nothing recomputes is a per-site chore that some site will
  eventually forget.

  A test already covered this present and asserted only `list`, which is what
  let it ship; the replacement asserts the invariant, that `record` is always
  derivable from `list`.

  One question this deliberately does not answer: whether the original client's
  book was monotonic — whether selling your last copy of a Companion should
  forget it. Every path here derives the book from what is currently owned, so
  it does forget, and that behaviour is unchanged rather than newly decided.

### Changed

- **The Pact of Fellowship now opens up as you play, instead of all at once.**
  The bundled pool was flat: a brand-new account could pull Ancient Sadness or
  Giant Nega — Chapter 38 characters — on its first 3,000-Coin draw. The
  community record describes the pool as cumulative instead, each chapter adding
  its own characters and keeping every earlier one, and roughly half the roster
  was reachable ahead of that. Fifty-four of the 103 members are available at
  Chapter 1; the other forty-nine arrive across twenty-one gates up to
  Chapter 38.

  Each member now carries the earliest chapter that can draw it, and a draw is
  filtered against your account's own story progress — the same chapter reading
  that already gates achievement claims and stage entry, not a new notion of
  progress. Fellowship Tickets pay differently but draw the same gated pool.

  **Two pools are deliberately left alone.** The Pact of Truth keeps its full
  roster: no comparable availability record was found for it, and borrowing
  Fellowship's curve would be inventing one. An operator-supplied catalog also
  keeps its pool whole, because a schema version 1 catalog carries no
  availability data to honour — the same restraint that already stops such a
  catalog from silently acquiring a Fate/Luck policy.

  This does not touch selection *odds*, which remain uniform within the pool and
  remain local policy rather than recovered service values.

## 1.0.5 — 2026-08-06

### Added

- **Orbling Cavern and Cryptid Forest are reachable.** Both draw a permanent map
  point on World 1 and neither had ever appeared, which several testers asked
  about. They were not partially implemented or subtly broken: they were absent,
  and the cause was a single missing thing on the server side.

  The client builds each point only if `EventManager.IsEnabledAny` finds an
  enabled event flag under a prefix -- `sp_ch_700` for Orbling Cavern and
  `sp_ch_701` for Cryptid Forest -- in the `eventFlags` object login and status
  send. This server had never sent a key under either, so neither point was
  constructed, and a map point that is never constructed reports nothing. The
  chapter identities are Confirmed from `ChapterInterface::.cctor`: 7000--7009
  is Orbling Cavern and 7010--7019 is Cryptid Forest, with sections only in 7000
  and 7010, so the two areas are four stages between them.

  Unusually, that flag is all the server can contribute. `UISpecialSelect`
  modes 1 and 2 read a hardcoded list apiece -- `["7000-1", "7000-2"]` and
  `["7010-1", "7010-2"]`, set in the client's own static constructor -- and
  never consult a served list the way the Archive selector consults
  `specialQuestList`. All four stages are therefore unadvertised, like the Daily
  Quests and the two secondary world maps, and the server's job is to honour a
  start rather than to publish a menu.

  Both areas cost one stamina and no Coins. Each Orbling Cavern card awards the
  one Companion its own `dropBuddies` manifest declares -- Bahl OIII on 7000-1
  and Grace OIII on 7000-2 -- and the reporter states the drop is guaranteed
  while that Companion is unowned and does not occur once it is held, so a later
  clear reporting nothing is ordinary rather than a fault. Each Cryptid Forest
  card farms one of Dracorin's two job-material sets: the client's Kirin
  constructors hand the engine items 150 and 151 on 7010-1 and 152 and 153 on
  7010-2, and the operator's own ChrDatabase independently prices Dracorin's
  first job at exactly 150 and 151 and its second at 152 and 153. Cryptid Forest
  also carries the Lucky Runner, which already had a Luck policy written for
  chapter 7010 and no stage to attach it to; a one-stamina entry still pays it,
  because the eight-stamina battle-end rule does not govern that source.

  Both open on the client's own gate: Cryptid Forest after Chapter 5 and Orbling
  Cavern after Chapter 6, read out of the `openChapter` each map point is built
  with. The server sends each area's flags no earlier, so a drawn point never
  leads to a start this server would refuse. Enabled by every launcher as part
  of the standard policy set, or on its own with `--cavern-forest`.

  One inference is recorded as withdrawn rather than quietly dropped. Orbling
  Cavern's sections declare `battleCnt` 0, which this project has read elsewhere
  as a stage with no battle program, and reading it that way here would have
  written the area off as an empty placeholder. Twenty-six chapters declare
  all-zero `battleCnt`, including two implemented Archive events and both
  Yamamoto Puzzle Quests and Lucky Orbling, all confirmed playable on hardware.
  See `docs/findings.md` for what actually distinguishes a placeholder.

  Physical-client confirmation of both selectors, and of the Companion award,
  remains pending.

### Fixed

- **`--disable-google-services` now stops the bind that actually crashes.** A
  Galaxy S26 on Android 16 crashed on launch with the flag correctly applied —
  `NoSuchMethodError` on `ServiceConnection.onServiceConnected(ComponentName,
  IBinder, IBinderSession)`, the same failure the flag exists to prevent.

  The flag rewrote 18 bind actions in the client's `classes.dex`. It turns out
  the crashing bind is not one of them and never was: Unity's own `libunity.so`
  binds Play Services from native code to read the advertising ID, using its own
  copy of `com.google.android.gms.ads.identifier.service.START` that no edit to
  the dex reaches. The flag now rewrites that copy too, in both ABIs.

  Only Unity's connection was ever vulnerable. It is built as a
  `java.lang.reflect.Proxy`, which hands an interface's `default` methods to its
  handler rather than inheriting them, so Android 16's new three-argument
  overload arrives at a 2017 bridge that has never heard of it. Every ordinary
  Java class inherits that overload correctly, and all twelve classes in the
  client dex that implement `ServiceConnection` are ordinary classes.

  That last point retracts the earlier diagnosis. A Galaxy S24 FE log showed
  `UnityIAP: Billing service connected.` immediately before the fatal and Play
  Billing was recorded as the crashing bind; billing's connection is
  `com.unity.purchasing.googleplay.BillingServiceManager$1`, an ordinary class,
  so it could not have thrown this and the line ordering was coincidence. The
  billing and Play Services actions stay neutralized — they cost nothing — but
  they are no longer described as the fault.

  The cost of the new edit is that Unity cannot read the advertising ID, which
  is analytics for a service retired years ago; Unity already handles the bind
  failing and has its own message for it. The self-hosted route was never
  affected, because its host guard catches the callback whatever caused the bind.

  Also corrected: how to tell whether a build carries the flag. On the
  separate-server route `/healthz` cannot answer it, and the generated plan must
  not be used either — it is rewritten by every setup run, so it describes the
  last build rather than the installed one. `docs/troubleshooting.md` now reads
  the installed APK instead. Physical confirmation that the extended flag clears
  the crash is pending.

## 1.0.4 — 2026-08-06

### Fixed

- **A Pact draw paid with Energy left the save failing its own validator.** The
  nested `valuables` block is a projection the client reads; the flat wallet
  fields beside it are what this server spends and grants. Keeping the two in
  step was a per-site chore, and most sites did not do it -- a Pact draw, an
  inbox present's Coins, a Rebirth, a stamina refill and a Trading Post
  exchange all moved the flat value and left the projection behind. A tester's
  exported save showed it after a ten-draw: `valuables.freeEnergy` read 72
  against `freeEnergy` 22, the difference being the fifty the draw had spent,
  and `account_state validate` refused the file.
  The projection is now rebuilt from the flat wallet on every persist, so it is
  an invariant of the save rather than something each mutation has to remember;
  every mutation already ends in a persist. Saves that drifted before this are
  repaired when they load, taking the flat value as the truth -- the
  disagreement is only ever the projection being stale, never the player having
  been charged twice.

- **An inbox present now pays out, and a stage started afterwards no longer
  hangs.** Opening a present displayed its rewards but credited nothing, and
  the next chapter stage froze. One cause: the read reply was shaped wrong at
  the top, so the client's callback died partway and left its copy of the
  account mid-update.

  The read-messages callback opens with `if (json.Contains("result"))` and then
  *rebinds its receiver* to `json["result"]`. Every field it goes on to read —
  the six wallet values, `buddyInfo`, `chrdata`, `itemList`, `summonList`,
  `achivementFlags` and `readlist` — is looked up inside that object, not
  beside it. This server answered `result: true` with those fields alongside
  it, so the client called `Contains` on a boolean and threw
  `InvalidOperationException: Instance of JsonData is not a dictionary`.

  Before that could even be reached, `AppServerUtil.callAPI` indexes `success`,
  `digest` and `lastupdate` off every response, unguarded, before dispatching
  to any endpoint callback. The mail routes answered `result` and nothing else,
  so the wrapper raised `KeyNotFoundException` first. Every other mutation
  already carried those fields, which is why only mail was affected.

  Both are fixed: the read reply nests its payload under `result` and both mail
  replies carry the wrapper fields. Verified on an emulator end to end — a
  present carrying 500 Coins, 3 Energy and two Metal Tickets moves the wallet
  from 1000 to 1500 on opening, and Chapter 3-1 then loads its squad screen and
  starts its battle with `start_quest` answering 200.

  The delete reply is canonicalized for the same reason the read reply already
  was: its digest is computed over the serialized text, so an unsorted payload
  signs differently once replayed from the save after a restart. The delete
  callback is not nested this way — it reads `deletelist` straight off the root.

- **A won Strikes Back battle now settles instead of stranding the client on
  its reward screen.** Clearing a Counter Descent stage showed the rewards, then
  looped Network Errors on the item screen and never added them
  ([#46](https://github.com/anzensan/project-liminal-gate/issues/46), reported
  against Spinetrich Kino Chapter 8000-1 on a Pixel 7 Pro).

  The family settled under a zero-base policy that required a clear to grant
  *nothing*: zero Coins, zero experience, no items, no monsters, no Lucky enemy,
  and the roster and inventory returned unchanged. That was adopted while the
  family's clear callback was unobserved, and a real won battle contradicts
  every clause of it. Each clear was refused with `invalid_local_event_result`,
  which reaches the client as an unsigned 409 — a transport failure, not an
  endpoint refusal — so it showed the network dialog and retried. The refusal
  also leaves the battle open, so the retry was refused identically, and the
  reward screen became a dead end. All fourteen packaged families were affected,
  not only the one reported.

  A Counter Descent clear now settles the way a Hunting clear does, which is the
  policy this server already applies wherever the surviving client is the only
  remaining account of what a battle paid: the report is trusted, and the
  inventory accompanying it must be exactly the durable counts plus the drops it
  declares, capped at the client's own stack ceiling, so the item array cannot
  become a grant channel beside the drops. Experience, Coins, Skill Boost,
  recruited monsters, and Lucky enemies are kept through the same trusted merge
  every other event and story clear uses, and a Companion drop stays bounded by
  the stage's own recovered `dropBuddies` manifest. A reported Summon is still
  refused: no recovered source states an event stage's Summon outcome.

  Chapter 1100 keeps the bounded shape this replaces — it is a real level-90
  battle whose experience a won fight must keep, and nothing else about its
  rewards was recovered.

- **The troubleshooting guide now points at the right request log.** It named
  `user-data/events.jsonl` unconditionally, which does not exist on the
  on-device route: that server writes to its own app-private
  `files/events.jsonl`. A tester following the old text found nothing and could
  reasonably read that as the server having refused nothing. Both locations are
  now documented, along with how to capture a logcat that actually contains the
  failure rather than ending before it.

### Added

- **An inbox present now shows the reward it carries.** Opening a present drew
  its text over an empty space: no Coins, no Energy, no items, no character, no
  Companion, and the plain "Message from the admin" heading rather than the
  gift one. The rewards were granted correctly the whole time; the client was
  never told about them.

  The reviewed client reads every reward out of a `gifts` entry and looks at
  nothing else. It never reads a top-level `coins`, `energy`, `chr`, `item`,
  `buddy`, `summon` or `title` — which is exactly what this server had been
  sending — so `Message.coins` and its siblings stayed zero, `get_hasGift`
  answered false, and the mail screen drew the no-gift presentation over a
  present that really did carry something.

  The shape was recovered by resolving the constructor's own key literals
  through the GOT relocations that supply them, which reads the keys out of the
  binary instead of guessing at them: `json["gifts"]` is indexed by integer,
  and inside an entry `coins`, `energy`, `chr`, `summon` and `title` are
  scalars, `item` is another integer-indexed array of `{id, num}` pairs, and
  `buddy` is one such pair. `title` lands on the client's `multiplayTitle`.
  `messages` is an object read by the keys `default`, `ja` and `en`, and `date`
  stays a JSON real even though the field is a `long`, because the constructor
  reads it through LitJson's `(double)` conversion.

  Verified against the reviewed client on an emulator across every reward
  channel: a present carrying 500 Coins, 3 Energy and two Metal Tickets now
  opens as "Gift from the admin" and lists all three, and one carrying a
  character and a Companion lists Joker Λ and Excalibur x 1 by name. Standard,
  because the shape it replaces cannot display a reward at all.

  Two earlier readings of the same class were wrong and are recorded here
  because of how they failed rather than that they failed. `date` as an integer
  and `messages` as a positional array each threw out of `Message..ctor` —
  `InvalidCastException: Instance of JsonData doesn't hold a double`, then
  `InvalidOperationException: Instance of JsonData is not a dictionary` — and
  the exception killed the login callback, leaving the client on `Connecting...`
  indefinitely with no error dialog. One malformed field in one message hangs
  the client on a loading screen; that is what a stall of this kind looks like
  from the outside, and it is worth knowing when a tester reports a freeze.

- **Daily login rewards now arrive through the original inbox** (issue 34).
  Guided core-story servers issue the published eight-day consecutive cycle
  and cumulative rewards for days 1--10, 30, 60, 100, and every 50th day
  thereafter. Eligibility turns over at 00:00 UTC. Same-day relogins do not
  duplicate a present, a missed UTC day resets only the consecutive count, and
  the cumulative count survives. Issuance commits with the account before the
  login response exposes either present; the existing inbox read/delete
  transaction then grants Coins and Energy once across retries and restarts.
  Login now projects only unread presents, so a claimed message cannot be
  reconstructed as a fresh menu badge; its durable record remains available
  for exact read replay and explicit deletion.
  The separately branded seven-day newcomer campaign is not folded into these
  standard rewards: its item and Companion identities remain a distinct event
  policy to audit.

- **The combined APK survives the Android 16 service-connection crash.**
  `HostedActivity` installs a main-thread guard before Unity starts. It drops
  exactly one error — `NoSuchMethodError` naming
  `ServiceConnection.onServiceConnected` — logs every occurrence under the
  `LiminalGate` tag, stops after 64 of them, and lets every other throwable end
  the process as it would have. Always on: it does nothing until an exception
  that would otherwise kill the app.
  This exists because the string patch below cannot finish the job. A device log
  showed the fatal bind arriving as `com.google.android.gms.ads.service.CACHE`
  *after* that action had been rewritten in the client, alongside `appset`,
  `safebrowsing`, `safetynet`, and `dynamiclinks` binds whose strings are absent
  from the client entirely: Play Services loads code into the process through
  Dynamite and binds with its own constants, which no edit to the APK can reach.
  Dropping the callback is equivalent to the bind never completing, which is the
  state the same reporter confirmed loads the game. Verified on an emulator by
  throwing the exact error on the main thread: swallowed once, UI still pumping
  three seconds later, no fatal. The separate-server route has no host DEX and
  is not covered.

- **`--disable-google-services` gets the client past an Android 16 launch
  crash.** The 2017 client dies on `NoSuchMethodError` in `bitter.jnibridge` the
  moment a Google Play Services bind completes: Android 16 added an
  `onServiceConnected(ComponentName, IBinder, IBinderSession)` overload, and
  Unity's `java.lang.reflect.Proxy` for `ServiceConnection` is handed `default`
  methods rather than inheriting them, so the 2017 bridge is asked for a
  signature it does not know. The bridge is Unity's and cannot be rebuilt, but
  the crash needs a *completed* bind, so the flag rewrites the final byte of
  each of 18 bind actions and the Intent resolves to nothing. Two are Google
  Play Billing: a physical Galaxy S24 FE log ends `UnityIAP: Billing service
  connected.` immediately before the fatal, which makes billing the confirmed
  cause. Play Billing lives in `com.android.vending`, a different package from
  Play Services, so the 16 Play Services actions — inferred from the same
  mechanism rather than observed — do not reach it. Play Games, the ads SDK, Google auth, and Nearby have no live service
  to reach. The two `ICommonService`/`ICommonCallbacks` binder descriptors are
  deliberately untouched. Available on both routes, since both install the same
  client. The patch plan schema is version 2: a dex edit invalidates the
  `checksum` the runtime enforces and the `signature` ART reports as
  `dex-id-...` and caches against, so patches declare `repair_dex_header` and
  both fields are recomputed. A dex `string_ids` table is also *sorted*, and an
  in-place edit preserves every offset but not the order, so plan generation
  refuses any replacement that would not still sort between its neighbours —
  an unsorted table is rejected by the runtime and the app dies at load.
  Not every Google interaction can be stopped this way: once GMS loads a
  Dynamite module into the app's process, that module binds using its own string
  constants, which no edit to the client's dex can reach.
  **Off by default, and it should not stay that way.** It rests on one Android
  16 device. A build carrying only the Play Services actions got that device
  past its launch crash and as far as the billing bind, so the mechanism is
  established; the billing actions that follow from its log are not yet
  confirmed to finish the job. Make it the default once a patched build reaches
  gameplay on Android 16 *and* one clean Android 14/15 run shows no regression.

- **The on-device save can be moved off the device.**
  `python3 -m liminal_gate.on_device_state export|import|update --device SERIAL`
  reaches the packaged Android build's save through the embedded server's new
  loopback `/local/state` route over `adb forward`. Until now that save had no
  route out at all: the app is not debuggable, so `run-as` is unavailable, and
  `adb backup` stopped carrying app data for release packages after Android 11.
  `export` changes nothing on the device and writes a full copy under
  `user-data/on-device-state/`. `import` refuses a file that breaks the client's
  invariants or that has lost an account the device holds, replaces the
  in-memory state and the file together so a running server cannot undo it,
  rotates the replaced save into `state.json.bak.1`, and restarts the app to
  confirm the result. `update` exports before it builds and never uninstalls —
  on a signing-key mismatch it stops and prints the recovery steps. Every
  workstation command in `liminal_gate.account_state`, including `adopt` for a
  reinstalled client's new UUID, now applies to an on-device save through the
  exported copy. The route is served only by a loopback-bound listener, so a
  LAN-bound server does not publish a downloadable, replaceable save to the
  network; on the device itself, any app can reach it while the game runs.

- **A toolchain doctor removes the `PATH` and `JAVA_HOME` step.**
  `python3 -m liminal_gate.doctor` reports which build tools this machine has;
  `--install-missing` fetches a Temurin JDK, the Android SDK packages through
  Google's own `sdkmanager`, pinned Android NDK r27d for its AArch64-capable
  `llvm-objdump`, Il2CppDumper v6.7.46, and — only where the managed dumper build
  needs one — a private .NET runtime. Direct archives are verified against
  published checksums, SDK/NDK packages use Google's repository verification,
  and everything — including the on-device builder's pinned Gradle distribution
  — lands under ignored `user-data/`. Locations
  are recorded in `user-data/toolchain.json` and replayed into the environment
  by `tester_setup` and `on_device_setup`, so no shell variable has to be
  exported in any terminal. A variable the operator set themselves still wins.
  The Android SDK licences are never accepted without being asked. Android
  Studio and emulator images remain the operator's choice; a system-wide LLVM
  installation no longer is.

- A source-only private on-device build path packages the tester's reviewed
  client, complete local resources, dual-ABI Python compatibility server, and
  readiness-gated launcher into one locally signed APK. Readiness identity is
  bound to the patched client, packaged content, and embedded host sources; the
  installer starts the exact replacement activity instead of relying on a
  one-event `monkey` command. Generated packages,
  resources, keys, state, and Android build products remain private/ignored;
  full physical-client and ARMv7 acceptance are still pending.

### Changed

- **`release_audit` no longer sweeps ignored, untracked material.** The audit
  reports what a clone of a release carries, and Git omits ignored files from
  every clone; sweeping them anyway buried the boundary findings the tool
  exists for under thousands of lines about a working checkout's own local
  inputs. On this repository it drops from 6071 findings to whatever is
  genuinely wrong. The skip list comes from `git ls-files --others --ignored
  --exclude-standard --directory`, whose `--others` is load-bearing: it lists
  only untracked paths, and Git does not apply ignore rules to a tracked file,
  so a committed `.apk` can never be skipped however `.gitignore` reads. The
  history scan is unchanged, a root that is not a repository is still swept in
  full, and `--include-ignored` restores the whole disk sweep for a release
  handed over as a directory rather than as a clone. `release_preflight` is
  deliberately untouched and remains the unconditional filesystem gate.

- **Only story and event clears pay preservation Energy.** Hunting, Metal Zone,
  the special quest, the Daily Quests, and the Chapter 1100 Roads paid the same
  per-stage award as a story stage, on the first clear and on every clear after
  it. Those areas repeat without bound, so the wallet's local income was really
  priced in Metal Zone runs: a Pact, a job unlock, or a stamina refill cost
  whatever a repeatable stage could be replayed enough times to cover. They now
  mint nothing and record no first-clear key, and the archive's only stage
  income is the story an account is actually advancing — unchanged rates, and
  the one-time chapter-completion award is untouched. The refusal lives in
  `archive_economy.ENERGY_BEARING_KINDS`, so a stage family added later has to
  state which side of the line it is on.

- **The stamina meter no longer gates quest entry, on any launcher.** Entry
  charges nothing, the bar the client draws stays full, and the refill route
  answers the client's own `NoNeedToRefill` instead of selling an Energy for a
  meter nothing spends. A save carrying a fill origin from a charged run is
  returned to full on the next `GET /gd/userdata` rather than reading back as a
  half-filled bar nothing will ever finish debiting.
  The recovered model is intact and unchanged: `--enable-stamina` runs
  `GameManager.CalcStamina` and `UserData.GetMaxStamina` exactly as before, and
  `scripts/install_systemd_service.sh PORT --enable-stamina` writes the flag
  into the systemd unit for a dedicated host. A refilling meter paces a live
  service; there is no longer a live service to pace. The client always draws
  the bar — it is `ServerConstants` and local `UserData`, not server-side UI —
  so off means a meter that is always full, not one that is hidden.
  The four entry routes now ask one `entry_stamina_origin` helper rather than
  repeating the same pair of `userdata` reads around `spend_stamina`.

- **One policy source for all three launchers.** Guided setup, the dedicated
  server, and the packaged Android host previously each carried their own copy
  of the gameplay-policy set (sixteen constant booleans threaded through the
  guided command builder, a literal flag tuple, and an inline JSON document),
  held together only by a drift-guard test. All three now derive from
  `server_config.STANDARD_POLICY_FLAGS`, so a recovered feature cannot ship
  enabled on one path and unreachable on another. Per-policy selection remains
  a `bootstrap_server` command-line capability, unchanged. The long-retired
  interactive-setup compatibility argument (`choose_local_server_options`'s
  `ask`) is gone with it.

- **A maintenance pass consolidated long-copied scaffolding** without behavior
  change: one shared `sha256_file`, one atomic JSON writer, one home for the
  reviewed-build identity and client inventory-shape constants, the profile /
  wire-encoding / request-parser layers lifted out of `bootstrap_server`, and
  shared test scaffolding replacing per-file copies across fifty test files.
  Command lines, generated-file bytes, and wire behavior are unchanged. The
  pass also fixed a latent builtin-`ImportError` shadowing in `tester_setup`,
  gave `native_encounter_importer` the `--force` overwrite guard its scenario
  sibling had, made the story-outcome generator refuse invalid baseline IDs
  before writing, and made an unmapped mutation result answer HTTP 500
  instead of crashing the handler thread.

### Fixed

- **Cryptid Forest paid a Lucky Orbling's Luck, and its enemy is a Lucky
  Runner.** The `allowLucky` source granted all five flagged chapters +0.3 at a
  50% chance. Chapter 7010 is `EidolonForestChapter` inside the client, which
  is how this repository recorded it, but its player-facing name is Cryptid
  Forest — and under that name the community record documents its enemies
  outright: one Lucky Runner always spawns, a second spawns with a 30% chance,
  and a pincer from any direction grants 0.1 to the whole party. The stage was
  therefore granting three times the documented Luck, from the wrong enemy, on
  a coin flip where a guarantee was stated. 7010 now takes the Runner's
  documented population and gain; the other four keep the Orbling policy and
  their draw sequence is unchanged, because the chapter is not seed material.
  The record's conditional 50% second spawn (a party carrying Dracorin Λ's
  *Cryptid Ruler*) and its app-restart suppression are recorded and not
  implemented, since this server models neither party skills nor client
  lifecycle. `roll_luck_up_table` now takes the stage's `lucky_chapter` instead
  of an `allow_lucky` flag each caller computed for itself — that duplication
  is what let the flag and the species disagree. See `docs/findings.md`,
  2026-08-05.

- **The Tavern kept playing the menu theme, and the live-recorded tracks were
  unreachable** (issue 44). Three of the flags the client reads to decide which
  track belongs to which screen were never sent, so every branch that would
  have switched music was skipped and whatever the previous scene started
  carried on. Reported as "Evening at the Tavern" never starting while the
  battle, boss, and victory transitions all worked; those are client-side scene
  changes that consult no flag, which is why only the menu-to-menu case showed
  it.
  `use_sakaba_bgm_for_bar` is the Tavern's own theme and
  `use_another_bgm_for_hunting` the Huntland equivalent. `EnableLiveMusic` cost
  the most: the one client method that names it also names `BGM100` through
  `BGM103`, so the live-recorded tracks are reachable through that flag and
  nothing else. Their bundles are in every tester's resource set and the client
  downloads them at startup, so the server was shipping five tracks to the
  device that nothing could ever play.
  All three now ride every login, ungated. Each selects audio and nothing else
  -- no stage, no item, nothing the save records -- so none is a policy an
  operator needs to choose. `UseLiveMusicAsDefault` and `ReverseTitleMusicOrder`
  remain deliberately unsent: both change a default rather than reach otherwise
  unreachable audio, and the retired service's value for each is unrecovered.

- **Luck could not grow anywhere except the ordinary story.** The preceding
  Luck fix stopped a stale client rolling the stat *back*, and it worked — a
  reporter confirmed a character kept its 10% across Metal Zone runs — but a
  second report that Luck never rose showed the preservation was the only half
  implemented. The server has three battle start/clear pairs and only the
  generic story one ever rolled a `luckUpTable`: Hunting Zones, Metal Zone, the
  Roads, every Daily Quest, and the Chapter 1100 Roads set no
  `active_luck_up` at entry, so their clears had nothing to apply. That silently
  excluded every stage the ≥8 stamina rule already qualified — Metal Zone zones
  2--7 at 8 to 20 stamina, the Roads at 15, Coin Creeps at 10 to 20, and Chapter
  1100 at 25. Both handlers now roll at entry and apply at clear, after the
  roster merge and once per battle, with the entry's table replayed rather than
  re-rolled. `LUCK_GAIN_MIN_STAMINA` is untouched: it is the developer's own
  confirmed rule, it reads the stage's *declared* cost rather than what the
  meter was charged, and so it never depended on `--enable-stamina` either way.
  No Luck Treasure Chest is authored on any of these stages; the community
  record's own no-chest list names the Hunting and Metal zones, and Chapter
  1100's chests stay refused as labeled local policy. `luckResult` accompanies a
  gain only as the six empty slots an ordinary story stage with no documented
  pool already sends.

- **The Lucky Orbling quest granted no Luck, which is the one thing it is for.**
  The recovered `allowLucky` flag is 1 on exactly five chapters — 2006 Lucia,
  3003 Money Money Time, 3004 Crystal Road, 6010 Lucky Orbling, and 7010 Eidolon
  Forest — and `docs/findings.md` reads it as "Lucky-type enemies may spawn
  here", a Luck *source* rather than the chest gate an earlier reading took it
  for. Nothing implemented it: `LUCKY_ORBLING_GAIN_TENTHS` and its pincer chance
  sat in `luck_data` unreferenced by any code path. A reporter saw 1.8 on every
  character during the quest and nothing in the party menu afterwards, which is
  the client rendering its own in-battle pincer and the server never hearing
  about it — the confirmed final client omits the optional `luck` member from a
  clear, so the gain has no way back. The five chapters now carry a server-side
  Lucky-enemy source, delivered through `luckUpTable` because that is the only
  channel the client renders a Luck gain through. It is deliberately *not*
  governed by the stamina gate, and it could not be: Lucky Orbling is free,
  Money Money Time costs five and Crystal Road seven, so folding it into the
  battle-end gain would leave the three stages the record most clearly documents
  as Luck sources unable to grant any. One invented number is added and isolated
  beside the existing one — `LUCKY_ENEMIES_PER_BATTLE`, how many pincer chances
  one battle on a flagged chapter offers. The record fixes the +0.3 gain and the
  50% chance but never states a population, and the spawn lives in client-side
  battle data this server does not read, so the invented claim is held to a
  count rather than a distribution.

- **An inbox present stranded the account it was delivered to.** A message
  carrying a character wrote that character onto the durable roster in the
  shape its own *response* carries — `isNew` and `levelAdded`, a one-element
  `jobLevels`, an empty `jobSlots` — rather than the generic record the save
  otherwise holds. Every settlement check reads the durable roster through
  `_valid_generic_character_record`, which requires the exact eight-key record
  and length-three arrays, so a single present refused every stage clear the
  account attempted from then on. Nothing recovered on its own, across
  restarts included: the roster merge that would have rewritten the row is
  only reached by a clear that was accepted first, so the one repair path was
  behind the refusal it caused. Reported as the client stalling on a character
  pull or on entering a stage after opening mail.
  The same row was written by four grant paths, not one: inbox presents, event
  stage characters, Hunting and Daily Quest grants, and the battle-recruit
  backstop. All four now persist the generic record — the Pact draw already
  drew this distinction, keeping the response shape out of the save — and the
  `isNew`/`levelAdded` a result screen reads are projected onto the response
  instead of stored. What the client receives is otherwise unchanged.
  Saves already carrying the bad row are repaired when the server next loads
  them, keeping the packed level, Skill Boost, and Luck the row accumulated
  while it was unusable. Only a row carrying *both* response-only keys is
  rewritten, which is the exact signature a grant left; the client's own
  free-roam roster write carries `isNew` alone and is left as it was sent.

- **Setup packaged a half-extracted resource tree without saying so.** The
  resource root was accepted on the strength of its nine category directories
  *existing*; nothing checked that any of them held a file. An `Illust/` or
  `Pieces/` that was empty or partly copied therefore passed every check, the
  manifest named only what was there, the build succeeded, and the package
  installed — and the first sign of trouble was the client reaching a screen
  whose artwork the package had never carried, stalling with the music still
  playing, days later and on someone else's device.
  Resolution now refuses a required category that contains no files at all,
  naming every empty one and the root to re-extract into, while the tester is
  still at a prompt that can fix it. Because the tree is the tester's own
  extraction there is no absolute count to check a partial one against, so each
  build also prints its per-category inventory and compares it against the last
  manifest written to the same data directory: a category that has *shrunk*
  since the previous successful build is reported as a warning naming both
  counts. A first build, or an unreadable previous manifest, simply declines to
  compare rather than refusing to build.

- **A Bahl starter was shown recruiting an Archer and given a Warrior.** The
  tutorial's Chapter 1-2 recruit is the generic that completes the Circle of
  Carnage against your starter — an Archer for Bahl, a Warrior for Grace — and
  the client picks that completion itself and animates it. The bundled profile
  named the Warrior outright, captured from a Grace run where the Warrior is
  the right answer, so the signed roster replacement overwrote what a Bahl
  player had just been shown. Every first-Pact outcome now declares its recruit
  beside its starter, and the two commit together when the outcome is selected;
  the grant and every later party projection resolve from that durable pair.
  Grace runs are unchanged. A save with no recruit field keeps the Warrior it
  was already granted, whichever starter it holds, rather than switching to a
  character its client never received.

- **The self-contained build served resources under only one of their two
  names.** Android caches many client bundles under a 32-hex-prefixed filename
  while the client asks for the logical name, so both spellings have to
  resolve. The filesystem manifest the separate server reads has always
  registered both; the packaged manifest the on-device APK carries registered
  only the on-disk spelling. Every prefixed resource therefore answered
  `resource_not_found` on the packaged build and the client reported a network
  error — the inbox is where testers hit it — while the identical content
  loaded correctly from a separate server. Nothing was wrong with the mail
  routes themselves: they are shared by all three launchers and were reached
  and settled normally. Both manifest builders now derive their URL set from
  one shared alias rule, and the packaged manifest points every alias at the
  same stored member rather than packaging the bytes twice. A resource tree
  that collapses two files onto one client URL is refused at assembly time, as
  the filesystem builder already refused it. This changes the packaged
  manifest and so the build id: on-device testers need a rebuilt APK, not a
  restart.

- **The stamina gauge read full over a meter the entry had already spent**
  (issue 31). Quest settlements answered without `refillStartTime`, and to this
  client that is not an omission: zero is its own representation of a meter that
  refilled at the epoch, so a silent settlement and a full bar are the same
  statement. A tester saw the bar return to full on leaving a cleared stage and
  stay full across a relaunch, then watched the next entry refused as
  insufficient against a gauge still showing maximum. The server's arithmetic
  was never wrong: entry debited the meter correctly, the durable origin
  survived restart, `GET /gd/userdata` reported it accurately, and the refusal
  was correct. Only the settlement callbacks were silent. All three now restate
  the post-clear origin — generic story and event, Hunting, and World Map
  Special — which is the entry's own post-spend value everywhere except an
  ordinary chapter boundary, where it is the full meter that boundary already
  grants. The tutorial's Chapter 1 clears are unchanged: those stages charge
  nothing, so a full bar is what their meter actually holds.
  This widens three response shapes beyond what capture confirmed. The
  justification is the same one behind the chapter-boundary refill already
  documented as local policy: the server knows the meter and the client cannot
  derive it, so declining to send it is a choice to let the bar go wrong.

- **`on_device_state` could not find the toolchain `doctor` had installed.**
  `liminal_gate.doctor` and `liminal_gate.on_device_setup` both succeeded on a
  machine where `on_device_state update` failed on a missing AArch64
  disassembler — and earlier, on missing build tools and SDK platform — with no
  flag able to correct it, since that command names only `--adb` and
  `--build-tools`. The doctor records where it put each tool in
  `user-data/toolchain.json`, and every launcher replays that record into its
  own environment before its first resolver runs; this one never did. It was
  the only entry point that missed the step, so the tools it needed were the
  ones deliberately kept off `PATH` — the privately installed pinned NDK
  `llvm-objdump` above all. `main` now replays the record ahead of everything
  else, for `export` and `import` as well as `update`, and a test asserts that
  ordering for all three.
  An operator has since confirmed both `export` and `update` from a Windows
  build host against a physical Pixel 7 Pro on Android 15 carrying real gameplay
  progress; `update` rebuilt and installed in place with the accounts intact.

- **`guided derivations` reported FAIL inside an activated virtual environment
  after an install that had really succeeded.** The same check passed in a plain
  PowerShell window, which is the shape of the report. The Windows launcher
  honours an active environment only when no version is spelled out, so
  `py -3 -m pip install ".[master-import]"` typed at a `(.venv)` prompt installs
  into the system Python; the check then reads `.venv`, which genuinely lacks
  the package. Nothing was wrong with either the install or the check — they
  were looking at different interpreters, and the documentation told the tester
  to use `py -3` for every command after creating the environment.
  Both messages raised by that probe now name the interpreter they actually
  read, quoted for a shell, so the printed remedy can no longer be the command
  that caused the failure. Inside an environment the message also names
  `sys.prefix` and says why a `py -3` install went elsewhere. The Windows
  instructions in `install-tools.md` and `on-device-setup.md` now stop at
  `py -3 -m venv`, which is correct because no environment exists yet, and use
  plain `python -m` from the `(.venv)` prompt onward; `troubleshooting.md`
  carries the symptom under both the setup checks and the PowerShell section.

- **Guided setup could not unpack Google's command line tools on Windows**
  (issue 38). `liminal_gate.doctor --install-missing` downloaded the archive,
  verified it, and then failed with `could not unpack
  commandlinetools-win-...zip: [Errno 2] No such file or directory` naming a
  file it was in the middle of creating. The archive names both a directory and
  the jar inside it `listenablefuture-9999.0-empty-to-avoid-conflict-with-guava`,
  which spends 165 characters before the destination contributes any; unpacking
  beneath a checkout in `Documents\GitHub` crossed Windows' 260-character path
  limit, and Win32 reports that as a missing file. Extraction, and the moves and
  deletions that follow it, now address the filesystem through the `\\?\` prefix
  that lifts the limit, and the staging directory has been shortened by twelve
  characters so the unprefixed path has room to spare as well. Archive members
  are still checked against the plain destination before anything is written, so
  nothing an archive may write has widened. Reported by @Cryo6325.

- **Hunting and Daily Quest clears no longer reject the original client's
  rewards just because a reconstructed ceiling is incomplete.** The client
  executes these battles and reports their Coins, EXP, items, recruits, and
  Companions at clear. The server now trusts that report by default after
  checking the exact active stage, wallet arithmetic, item projection,
  ticket-spend reconciliation, Companion-box integrity, and durable one-time
  settlement. `--outcome-strict` restores per-stage catalog maxima as an audit
  mode. This directly accepts the Pixel 7 Pro Crystal Road result that reported
  280 Coins and 5,400/5,625 EXP against the old zero placeholders. Companion
  IDs still need catalog level data because the server must author a row the
  clear form does not contain.

- **A game over in a Daily Quest no longer ends in a Network Error.** The
  client offers Continue when a Daily Quest is lost and posts `/gd/continue`
  for it, but the server accepted Continue only in the generic-story phase, so
  a Hunting battle — which every Daily Quest is — answered
  `continue_unavailable` at 409 and the client showed a transport failure with
  no way past it. Continue now applies the same coin policy to a Hunting
  battle. Chapter 1100 stays excluded, as its own notice requires: it runs as a
  world-map special. A Continue that genuinely cannot be offered is now
  soft-refused on `cmdError` like an out-of-rotation Daily Quest entry, so the
  client shows its own message rather than a transport error.

- **An abandoned battle no longer strands the account.** Nothing the client
  sends on the way out of a lost battle released the open stage, and a Daily
  Quest could not be re-entered to release it either — the day is spent at
  accepted start, so the client greys out the one stage that would have. Every
  other quest then answered 409 until the UTC day rolled over. A start for a
  different stage now counts as the player having left, since the client runs
  one battle at a time. Explicit local policy, alongside the existing release
  on a roster or party save. The spent day still stands.

- **Guided setup starts the server against the resource root it built the
  manifest from.** `--resource-root` accepts any of the enclosing directories
  and setup reports the `data_u2017/android` directory it detected inside one,
  but the launch that followed was handed the operator's own argument. Every
  mapped file was then looked up a level or more too high, so a setup that had
  just built and installed the APK ended on `resource file is unavailable`
  instead of serving. The detected directory is now resolved once and used for
  both. `server_setup` and `on_device_setup` were already correct.

- **The setup rehearsal finds the tools the doctor installed.** Every run gets
  an empty data directory, and guided setup replays recorded tool locations
  from the data directory it is given, so a machine provisioned by
  `liminal_gate.doctor --install-missing` failed the rehearsal's own
  prerequisite check on an Il2CppDumper it had. The record is now copied into
  the run; `--toolchain` names it when the doctor was run with a different
  `--data-dir`.

- **A Yamamoto Puzzle Quest clear no longer wedges the account** (issue 29).
  6011-1 and 6011-2 are the only two Daily Quests whose own `BattleData` section
  declares a `dropBuddies` manifest, and their two packed codes decode to
  Companion 267 and Companion 140 at one copy each. The bundled policy declared
  no Companion for any Daily Quest, so the client rolled the drop its own data
  allows, reported it, and had the whole clear refused with `409
  invalid_local_hunting_result` — which never releases the active battle, so
  every unrelated stage was refused afterwards too, across restarts. Both
  Companions now settle, at level 1 and at most one per clear; the other twelve
  quests still refuse a reported Companion outright. To recover an already
  wedged save, replay the same Puzzle Quest and finish it: re-entering a stage
  that is already active does not charge or consume the day again.

- **Three more Daily Quest ceilings that could refuse an honest clear.** All
  fourteen stages carried a zero EXP ceiling, which refuses the ordinary battle
  EXP a Daily Quest pays and which Metal Runner Rampage pays *only*; both Puzzle
  Quests bounded just their first reward tier, not the Tears, Particles and Ores
  the later tiers pay, and allowed roughly a third of the item total their waves
  can hold; and Rarity Rumble's Ores and Tearjerker Time's Tears and attribute
  rings were not declared at all. Each would have produced the same wedge on the
  stage that hit it. A bound in a client-settled family is only ever safely too
  generous, never too tight, and this family's bounds now say so.

- **A refused settlement now records which channel it refused.** The diagnostic
  logged chapter, section, coins and EXP, so eleven logged refusals of the same
  clear could not say whether an item, a Companion, a recruit or a Summon was at
  fault. It now also records how many of each a result claimed — counts only,
  never an identity or a string from the body.

- **The Hunting Zone selector flashed around Attack of the Coin Creeps.** The
  rows drew correctly and then the whole list strobed behind a loading circle,
  while Metal Zone and Strikes Back stayed perfectly stable. No request failed,
  because nothing was being requested.

  The client checks a selector row twice under two different rules.
  `UISpecialSelect.IsQuestOpen` excuses Chapters 1000--1099 from needing an
  `sp_ch_<chapter>-<section>` flag, and that is what builds the list — so the
  rows appeared. But the per-frame recheck in `UISpecialSelect.UpdateItems`
  calls `CheckQuestFlag` directly with no such exemption, drops every row that
  fails it, and then restarts the list-refresh coroutine, which rebuilds the
  rows so the next frame can drop them again.

  The server had been withholding flags for exactly Chapters 1000--1099,
  trusting the first rule. That covered all four tier-1 Hunting families and
  nothing else, which is precisely why the other selectors were unaffected.
  Every advertised row now carries its own exact section flag. (issue 20)

## 1.0.3 — 2026-08-01

### Added

- **Chapter 1100 now settles a Companion.** Each section's own recovered
  `dropBuddies` manifest admits at most one reported Companion per clear, minted
  at level 1, alongside the bounded experience. The community record's
  per-battle candidate lists match the manifests exactly; its roll weights, item
  drops, difficulty schedule, and the battle-4 character recruit remain refused.
- **Dragon Road grants its Steel Dragon recruit.** Re-reading the three
  recovered Road flags channel by channel found the earlier "drops nothing"
  reading too broad: empty `dropBuddies` rules out Companion drops and
  `allowLucky` 0 rules out the Luck chest, but `doNotDropExchangeItem` governs
  exchange items by its own name, and none of the three addresses
  battle-recruited monsters. Recruits are now bounded per stage through a
  declared `monster_recruit_maxima` rather than refused everywhere.
- The Trading Post rotation is anchored to a dated real-world Friday rather than
  to the epoch, and further external-reference findings are applied as labeled
  bounded policy.

### Fixed

- The setup rehearsal handled `--reuse-il2cpp` and resource roots given above
  `data_u2017/android`, both of which failed an otherwise successful run.

- **A changed IP address emptied the entire world.** Tower, Eidolon, Strikes
  Back, Archive, Metal Zone, and Hunting would all vanish from the client's
  menus at once, leaving a server that appeared to support none of them.

  The client fetches `get_server_status` *before* it logs in, and that response
  carries every stage list. Resolving which account is asking fell back to "the
  only account on this save" — but only while no client host had ever been
  bound. After the first login bound one, a device arriving on a new address
  resolved nothing, and the lists came back empty. The login immediately
  afterwards re-bound the address, so the save was never wrong and gameplay kept
  working; the menus for that session were simply built from nothing. A router
  lease renewal was enough to trigger it.

  The fallback now depends only on the save holding exactly one account, which
  is the condition that was doing the real work: with one account there is no
  second player to expose, these lists say only which stages exist, and reaching
  an account still requires its UUID. With two or more accounts an unrelated
  address resolves nothing, exactly as before.

  Relaunching the client was always enough to recover, because by then the login
  had bound the new address — which is also why this could look intermittent.

## 1.0.2 — 2026-08-01

### Changed

- **The verified original-client boundary is now Chapter 9**, played
  continuously on physical hardware with no client-visible failure. Chapter 2-1
  remains the deepest point backed by preserved request traces; the two answer
  different questions — whether the wire shapes are exact, and whether the game
  is actually finishable — so both are recorded rather than one replacing the
  other.

### Fixed

- **A Chapter-1100 clear could add characters to the roster.** Paying that
  chapter's experience in 1.0.1 meant accepting a changed roster, because levels
  live in it — but the check that replaced was requiring the roster back
  *unchanged*, so the loosening also let a submitted roster name someone the
  account never held. That is exactly the grant the same clear's Companion check
  refuses, arriving through another door. Levels may now advance; the set of
  characters may not.
- The inbox read no longer touches the account when a message grants neither a
  character nor a Companion, so an ordinary coin present cannot create a roster
  or Companion box that was not already there.
- `setup_rehearsal --keep` now prunes only directories it named itself
  (`YYYYmmdd-HHMMSS`). Recursive deletion was applied to whatever `--run-root`
  contained, and that argument is an ordinary path an operator can mistype.

## 1.0.1 — 2026-08-01

### Fixed

- **Dragon Road, Machine Road, and the Chapter-1100 routes rejected the battles
  you won.** All three had a zero experience ceiling, so a clear reporting any
  EXP — which every won battle does — returned `409` and the stamina was
  already spent. 1.0.0 documented this as "these areas award nothing"; that was
  wrong twice over. They do not award nothing, and what they were doing was
  worse than awarding nothing.

  Reading the sections out of the APK settled it. Each declares the absence of
  the *other* rewards itself: empty `dropBuddies`, `allowLucky` 0, and on the
  Roads `doNotDropExchangeItem` 1. So Coins, items, and Companions are still
  refused, now on the game's own authority rather than for want of evidence.
  Experience was never one of those channels — and the Roads are species-locked
  training zones (`species` 128 Dragon and 256 Machine at `assumedLevel` 35),
  where gaining it is the entire purpose of entering.

  Both now pay experience, bounded by a ceiling derived from the same selector's
  own tiers: the Roads' assumed level 35 sits between Metal Zone 3 and 4, and
  the higher neighbour is taken; a single Chapter-1100 battle is bounded by
  Metal Zone 7's five-battle allowance. The bounds err high on purpose. They
  exist to stop a tampered client, and a bound that is too tight refuses honest
  clears — which is the failure being fixed.

## 1.0.0 — 2026-08-01

The first release. What 1.0 claims is narrow and deliberate:

> Every single-player system the retired client had is present, playable, and
> restart-safe, with reward settlement explicitly labeled local preservation
> policy.

It does **not** claim historical fidelity. Where the retired service computed a
value and the client only rendered it, this server either labels its own choice
as local policy or refuses rather than inventing one. See
[PARITY_ROADMAP.md](PARITY_ROADMAP.md) for the three-way split between what is
implemented, what is permanently unrecoverable, and what is still open.

### Playable

Bootstrap, tutorial, and ordinary story Chapters 2--42 · Fellowship and Truth
Pacts including the Fate variant and the permanent Item 81 ticket draw ·
Companion draw, sale, strengthen, evolution, and the full equipment lifecycle
with party selection · job unlock, Rebirth, status-up items · Battle Summon
skill progression across all 44 recovered tiers · Trading Post with its
eight-week, 126-offer rotation · Hunting, Metal Zone, Money Money Time, Crystal
Road, and the two Roads · all fourteen Daily Quests · Archive Special Quests,
the Tower solo adapter, solo Eidolon quests, and eight Strikes Back families ·
Chapter-1100 world-map routes · inbox lifecycle with the retail chapter-ticket
presents · hash-validated serving of your own resource tree.

### Added in this release

- **Setup rehearsal** (`liminal_gate.setup_rehearsal`) — one command reruns the
  entire real setup pipeline on a clean copy of the source in an isolated
  environment, drives onboarding over real HTTP across a server restart, and
  compares every input hash, artifact hash, catalog count, and transport result
  against a baseline. The unit suite fakes the IL2CPP dump, the master-data
  import, the catalog derivations, and the signing; this covers what it cannot.
  See [docs/setup-rehearsal.md](docs/setup-rehearsal.md).
- **Daily Quests** — all fourteen recovered stages, resolved by matching every
  APK banner texture against the community record's own banner images, gated
  once per UTC day, and now enabled by both launchers.
- **Character and Companion inbox rewards** — the client's `chr` and `buddy`
  message channels are settled durably. A read that cannot deliver every reward
  it displays refuses rather than settling the affordable half. `summon` and
  `title` are refused at catalog load: no owner is modeled for either, and a
  displayed-but-undelivered reward is worse than an honest refusal.

### Fixed

- **The server could not start from the command line.** `--daily-quests` was
  defined by the parser and read by `main`, but never carried by
  `ServerConfig`, so every launch — including the one guided setup performs —
  died with `AttributeError` before serving a request. A structural test now
  requires every launch option `main` reads to be a field the configuration
  carries.
- **A feature could reach no operator.** Guided setup and the dedicated server
  built their flag lists independently, so Daily Quests shipped complete and
  unreachable. A test now requires the two launchers to enable the same
  gameplay policies in both directions.

### Documented

- Dragon Road, Machine Road, and the Chapter-1100 routes cost stamina and award
  nothing, because the operator's own game data carries no reward table for
  them. This is now stated plainly for players in
  [docs/scope-and-status.md](docs/scope-and-status.md) rather than left to look
  like a fault.
- The parity roadmap now separates work still to do from evidence that no
  longer exists — Luck Treasure Chest contents, Pact odds, event banner rates,
  and the Trading Post's rotation phase are closed questions, not backlog.
