# Solo event completion audit

Date: 2026-07-31

Scope: final Android 5.5.7-170 solo content reached from Arena or its Special
Quest selectors. Arena VS, Photon rooms, rankings, Co-op, Raid, and Donation
remain deliberately disabled.

> **Superseded on 2026-08-07, for Chapters 9100--9102 only.** This audit treats
> that range as Donation and excludes it, here and in the Tower row below. The
> range label is the client's; the content in it is Melting Pot, and the two
> client functions that justified excluding it are dead code in the final build.
> All 45 sections are now generated and advertised. Everything else in this
> audit stands as written. See `findings.md`, 2026-08-07.

## Client selector authority

The normal Special Quest selector is server-driven when the server supplies a
nonempty list. `UISpecialSelect.SetMode(0)` reads
`ServerConstants.specialQuestList` at static offset `0x190` on ARM64 and
`0x114` on ARMv7. It checks for at least one element and only then falls back
to `UISpecialSelect.specialQuestList`, the embedded 50-entry array. The relevant
method addresses are ARM64 `0xF84588` and ARMv7 `0xA8DBEC`.

This corrects the earlier interpretation that the embedded array was the only
possible list. The server can publish additional packaged solo stages without
patching the client, but it must still use a presentation identity understood
by the selector:

- a folded chapter card such as `2000`, backed by `sp_ch_2000`; or
- an explicit section card such as `2005-3`, backed by `sp_ch_2005` or
  `sp_ch_2005-3`.

The generated catalog now records `selector_id` separately from the exact
start/clear identity. A folded identity is deduplicated across all of its
cataloged sections. The loader refuses a folded card with a section-only flag,
which would render a card the client could not open.

Confidence: **Confirmed, dual ABI**.

## Curated Archive inventory

Guided setup derives 42 playable stages across these 17 Archive chapters from
the operator's matching BattleData and character catalog:

| Chapters | Presentation | Local story gate | Local first-section character grant |
| --- | --- | ---: | --- |
| 2000--2002 | one folded card per chapter | 2 / 10 / 20 | 148 / 144 / 151 |
| 2003 | explicit section | 20 | 596 and 597 |
| 2004 | explicit section | 4 | 673 |
| 2005 | three explicit sections | 13 | 736 |
| 2006--2009 | one folded card per chapter | 13 / 10 / 15 / 30 | none / none / 805 / none |
| 2010--2011 | one explicit section each | 31 / 32 | none |
| 2014 | one explicit section | 10 | none |
| 2015 | sections 1--3 only | 20 | 1080 |
| 2016 | two explicit sections | 30 | none |
| 2017 | five explicit sections | 20 | none |
| 2018 | one explicit section | 20 | 1288 |

The permanent gates and associated-character grants are explicit local archive
policy, not recovered production dates or reward transactions. Entry stamina
and Coins come from the operator's BattleData. No fixed clear-Coin reward is
invented; the event result reconciles client-reported battle Coins through the
existing durable transaction.

All selected chapters have compiled `Chapter2000`--`Chapter2018` native battle
programs in the final client. The matching Android archive inventory records a
background for every selected chapter and a matched section banner for every
published explicit section. The otherwise missing root banners for Chapters
2010 and 2011 are not requested because those entries use their matched
`sp2010-1` and `sp2011-1` section banners.

The generator deliberately excludes:

- Chapter 2012: three attribute-test stages, not release-facing quests;
- Chapter 2013: a bannerless memory row absent from the released selector
  catalog; and
- Chapter 2015 sections 4--6: titled `空き`, zero battles, and no section
  banners.

Confidence: **Confirmed** for identities, BattleData economics, native program
presence, and archived resource coverage; **local policy** for gates and
grants; **unrecovered** for historical schedules and complete reward tables.

## Other solo selector families

| Family | Implemented boundary | Client proof still required |
| --- | --- | --- |
| Money Money Time | Chapter 3003-1, including the observed 1,800-Coin ceiling and successful result-screen retry | no open settlement boundary for the observed result |
| Strikes Back | 8000--8007 and 8012--8017 through folded Counter Descent cards, advertised as bare chapters and flagged per section | open one card and confirm it expands to its real tiers only, then one clear/result return and the added 8012--8017 banners |
| Battle Champs / 8-Bit Rush | 8008--8011 as folded two-tier cards and 8018-1 as a section row, advertised in Arena -> Special Quests, with each clear bounded by its own `dropBuddies` manifest | confirm the four cards expand to two tiers each in the Special Quest menu, then one tier II clear that reports a declared Companion and one result return |
| Descent Quests | the seven Third Descent, Dragon King and Royal Rings rows moved onto the mode 3 `descentQuestList` | confirm the Arena menu draws all seven and that Special Quests no longer lists them, then one clear from the new menu |
| Tower | all 12 stages in 9010--9013 as a labeled solo adapter; Donation 9100--9102 excluded | first-stage clear and result return; navigation/entry already observed |
| Solo Eidolon | the 12 nonzero-battle, banner-backed stages in 4100--4111; 16 empty tier placeholders excluded | confirm every corrected banner, then entry and clear/result; collectible mapping remains capture-gated |

## Generated result and validation boundary

Against the retained APK-matched local inputs, the corrected generator produces 124
stages across 47 event families: 42 Archive stages, 58 bundled Counter Descent
stages, 12 Tower stages, and 12 solo Eidolon stages. At full story progress the
normal Special Quest list contains 26 curated Archive cards; the separately
bundled Money Money Time card is merged by the Hunting policy.
The corrected event catalog SHA-256 is
`1b99bc264ac6dbba4f81f4d89105e54e804b9f12cdaa4078d516886b3044ceeb`.

Focused warning-strict validation passed 139 tests covering schema refusal, folded-card deduplication,
placeholder exclusion, character association, progress gates, real-HTTP list
projection, folded non-first-section entry, clear mutation, retry, and restart.
Those tests establish the local transport contract. They do not certify that
every packaged battle program completes on the physical client. The complete
warning-strict repository suite passed all 653 tests in 128.357 seconds;
compilation, profile JSON, endpoint YAML, and diff checks also passed.

## Completion boundary

Before the broader solo event goal can be called complete:

1. ~~regenerate and deploy the 140-stage catalog~~ — deployed at commit
   `5302fb0`, catalog SHA-256
   `364048ce39141cad2712aba16561864bad9ad75a612c18c2f6c79bb2f753a863`;
2. ~~confirm multiplayer remains exactly disabled~~ — live response remains
   `enable=false, enablemain=false`;
3. ~~smoke one folded Archive card~~ — the physical final client opened the
   single Bahamut `2000` card and showed all four sections; one injected late
   explicit card remains to be checked after its story gate;
4. clear one Strikes Back stage, the entered Tower stage, and one solo Eidolon
   stage through their result screens; and
5. record any family-specific failure as a bounded work packet rather than
   replacing it with generic success.

## Physical-client certification sequence

Run these from the current Chapter 8 save without editing progression or
inventory. Preserve the server event tail and before/after save hash for every
clear.

1. **Confirmed:** Arena -> Special Quests presents one folded Bahamut card
   (`2000`), and it reveals all four cataloged sections. The maintainer observed
   this on the physical final client; the Beelink tail records the matching
   fresh login/status session but no battle start.
2. Clear Bahamut 2000-1. The result must return to free roam, release the active
   quest, and grant character 148 no more than once.
3. Clear Strikes Back 8000-1. Its result must return to free roam with a zero
   base reward and no second settlement on retry.
4. Clear Tower 9010-1. Its result must return to free roam without creating
   shared-HP, ranking, Donation, or story-progression state.
5. Open all twelve corrected Eidolon cards and verify their banners. Then clear
   4100-3 while preserving the exact request, result, and before/after owned
   Eidolon vector. Use that capture to establish whether and how the final solo
   quest awards a collectible before enabling any generated acquisition ceiling.
6. After normal story progress reaches Chapter 10, open injected explicit card
   2014-1. This distinguishes server-list ownership from the embedded fallback;
   earlier Archive cards alone cannot prove that boundary.

Selector navigation without a matching start/clear/result cycle proves only
presentation. A local HTTP replay without the final client proves only the
server transaction. Keep both claims separate.
