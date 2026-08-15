"""Trading Post offers from the retired service's weekly rotation.

`TRADING_POST_WEEKS` holds one tuple per week of the rotation, each row being
``(offer_id, target_item_id, target_buddy_id, target_count, stock,
cost_item_id, cost_count)``.  Exactly one of the two target IDs is set: the
client's offer record carries both ``targetItemID`` and ``targetBuddyID`` and
reads whichever is nonzero.  Offer IDs are unique across the whole rotation, so
the same trade appearing in two weeks appears twice with different IDs.

Unlike every other bundled policy in this package these values are **not**
recovered from the client.  The Trading Post was server-fed, so its offers exist
nowhere in the APK.  They come from the community wiki's rotation page, whose
eight collapsible sections are the eight weeks; every target and cost name in
that table resolved cleanly against the client's own master data, which is the
reason to trust the mapping.

The rotation's **phase** is community-dated rather than guessed.  The wiki's
rotation page was created alongside version 5.5.0 and then extended live: one
"Added trade" edit per Friday, 2018-10-12 through 2018-11-23 (revisions 83636,
83691, 83731, 83763, 83788, 83825, 83834), closing with "Rotation finished" on
Friday 2018-11-30 (revision 83859) when the cycle looped back to the first
table.  The archived official 5.5.0 news post dates the feature's launch to
2018-10-10 00:00 UTC with the first table live, which puts week one's Friday
boundary at 2018-10-05.  Table order in revision 84575 is the order the tables
were added, so the bundled week order is the historical week order and
`exchange_catalog` anchors the cycle to that 2018-10-05 Friday.  The fixed
cycle only existed from 5.5.0 onward -- the 2016--2018 weekly offers logged on
the wiki's yearly Trades pages do not match these eight tables -- and no
service capture confirms the cycle ran unchanged to the end of service; the
wiki page's two years of edit silence after 2018-11-30 is the evidence it did.

One thing the source does not establish: a traded Companion's level is fixed
by neither the client contract nor the wiki; these mint at level 1, matching
the Companion draw.

Sources: `Trading Post/Trades/Rotation`, terrabattle.fandom.com, revision
84575 and the revision history above;
web.archive.org/web/20181223215307/http://www.terra-battle.com/en/news/2018/10/ver-550.html.
"""

from __future__ import annotations

# Per week: (offer_id, target_item_id, target_buddy_id, target_count, stock,
#            cost_item_id, cost_count)
TRADING_POST_WEEKS: tuple[tuple[tuple[int, int, int, int, int, int, int], ...], ...] = (
    (
        (1, 0, 344, 1, 1, 181, 5000),
        (2, 0, 346, 1, 1, 181, 2500),
        (3, 0, 348, 1, 1, 181, 5000),
        (4, 0, 350, 1, 1, 181, 5000),
        (5, 0, 352, 1, 1, 181, 5000),
        (6, 0, 430, 1, 1, 181, 5000),
        (7, 0, 292, 1, 1, 181, 5000),
        (8, 0, 89, 1, 1, 181, 4000),
        (9, 0, 70, 1, 3, 181, 400),
        (10, 0, 186, 1, 3, 181, 300),
        (11, 99, 0, 1, 1, 181, 3000),
        (12, 94, 0, 1, 3, 181, 1500),
        (13, 118, 0, 5, 4, 181, 600),
        (14, 0, 130, 1, 20, 181, 2000),
        (15, 0, 129, 1, 20, 181, 800),
        (16, 137, 0, 5, 4, 181, 1500),
    ),
    (
        (17, 0, 419, 1, 1, 181, 5000),
        (18, 0, 427, 1, 1, 181, 5000),
        (19, 0, 428, 1, 1, 181, 5000),
        (20, 0, 429, 1, 1, 181, 5000),
        (21, 0, 487, 1, 1, 181, 5000),
        (22, 0, 19, 1, 1, 181, 5000),
        (23, 0, 124, 1, 1, 181, 4000),
        (24, 0, 83, 1, 3, 181, 400),
        (25, 0, 135, 1, 3, 181, 300),
        (26, 98, 0, 1, 1, 181, 3000),
        (27, 95, 0, 1, 1, 181, 3000),
        (28, 119, 0, 5, 4, 181, 600),
        (29, 0, 130, 1, 20, 181, 2000),
        (30, 0, 129, 1, 20, 181, 800),
        (31, 112, 0, 1, 5, 181, 100),
    ),
    (
        (32, 0, 274, 1, 1, 181, 5000),
        (33, 0, 278, 1, 1, 181, 5000),
        (34, 0, 486, 1, 1, 181, 5000),
        (35, 0, 280, 1, 1, 181, 5000),
        (36, 0, 281, 1, 1, 181, 5000),
        (37, 0, 394, 1, 1, 181, 5000),
        (38, 0, 79, 1, 1, 181, 5000),
        (39, 0, 44, 1, 1, 181, 4000),
        (40, 0, 165, 1, 3, 181, 400),
        (41, 0, 132, 1, 3, 181, 300),
        (42, 132, 0, 1, 3, 181, 1500),
        (43, 96, 0, 1, 1, 181, 3000),
        (44, 120, 0, 5, 4, 181, 600),
        (45, 0, 130, 1, 20, 181, 2000),
        (46, 0, 129, 1, 20, 181, 800),
        (47, 55, 0, 1, 20, 181, 100),
        (48, 54, 0, 1, 20, 181, 100),
    ),
    (
        (49, 0, 431, 1, 1, 181, 5000),
        (50, 0, 432, 1, 1, 181, 5000),
        (51, 0, 442, 1, 1, 181, 5000),
        (52, 0, 484, 1, 1, 181, 5000),
        (53, 0, 452, 1, 1, 181, 5000),
        (54, 0, 31, 1, 1, 181, 5000),
        (55, 0, 123, 1, 1, 181, 4000),
        (56, 0, 37, 1, 3, 181, 400),
        (57, 0, 188, 1, 3, 181, 300),
        (58, 97, 0, 1, 1, 181, 3000),
        (59, 93, 0, 1, 3, 181, 1500),
        (60, 121, 0, 5, 4, 181, 600),
        (61, 0, 130, 1, 20, 181, 2000),
        (62, 0, 129, 1, 20, 181, 800),
        (63, 81, 0, 1, 20, 181, 100),
    ),
    (
        (64, 0, 269, 1, 1, 181, 5000),
        (65, 0, 270, 1, 1, 181, 5000),
        (66, 0, 271, 1, 1, 181, 5000),
        (67, 0, 272, 1, 1, 181, 5000),
        (68, 0, 273, 1, 1, 181, 5000),
        (69, 0, 485, 1, 1, 181, 5000),
        (70, 0, 293, 1, 1, 181, 6000),
        (71, 0, 43, 1, 1, 181, 4000),
        (72, 0, 163, 1, 3, 181, 400),
        (73, 0, 185, 1, 3, 181, 300),
        (74, 95, 0, 1, 1, 181, 3000),
        (75, 132, 0, 1, 3, 181, 1500),
        (76, 118, 0, 5, 4, 181, 600),
        (77, 0, 130, 1, 20, 181, 2000),
        (78, 0, 129, 1, 20, 181, 800),
        (79, 133, 0, 1, 3, 181, 3000),
    ),
    (
        (80, 0, 354, 1, 1, 181, 5000),
        (81, 0, 383, 1, 1, 181, 2500),
        (82, 0, 393, 1, 1, 181, 2500),
        (83, 0, 279, 1, 1, 181, 5000),
        (84, 0, 395, 1, 1, 181, 5000),
        (85, 0, 25, 1, 1, 181, 5000),
        (86, 0, 107, 1, 1, 181, 4000),
        (87, 0, 36, 1, 3, 181, 400),
        (88, 0, 110, 1, 3, 181, 300),
        (89, 93, 0, 1, 3, 181, 1500),
        (90, 97, 0, 1, 1, 181, 3000),
        (91, 119, 0, 5, 4, 181, 600),
        (92, 0, 130, 1, 20, 181, 2000),
        (93, 0, 129, 1, 20, 181, 800),
        (94, 112, 0, 1, 5, 181, 100),
    ),
    (
        (95, 0, 290, 1, 1, 181, 5000),
        (96, 0, 291, 1, 1, 181, 5000),
        (97, 0, 295, 1, 1, 181, 5000),
        (98, 0, 333, 1, 1, 181, 5000),
        (99, 0, 342, 1, 1, 181, 5000),
        (100, 0, 450, 1, 1, 181, 5000),
        (101, 0, 13, 1, 1, 181, 5000),
        (102, 0, 42, 1, 1, 181, 4000),
        (103, 0, 68, 1, 3, 181, 400),
        (104, 0, 87, 1, 3, 181, 300),
        (105, 96, 0, 1, 1, 181, 3000),
        (106, 99, 0, 1, 1, 181, 3000),
        (107, 120, 0, 5, 4, 181, 600),
        (108, 0, 130, 1, 20, 181, 2000),
        (109, 0, 129, 1, 20, 181, 800),
        (110, 53, 0, 1, 20, 181, 100),
        (111, 56, 0, 1, 20, 181, 100),
    ),
    (
        (112, 0, 454, 1, 1, 181, 5000),
        (113, 0, 456, 1, 1, 181, 5000),
        (114, 0, 457, 1, 1, 181, 5000),
        (115, 0, 458, 1, 1, 181, 5000),
        (116, 0, 459, 1, 1, 181, 5000),
        (117, 0, 80, 1, 1, 181, 5000),
        (118, 0, 122, 1, 1, 181, 4000),
        (119, 0, 38, 1, 3, 181, 400),
        (120, 0, 131, 1, 3, 181, 300),
        (121, 94, 0, 1, 3, 181, 1500),
        (122, 98, 0, 1, 1, 181, 3000),
        (123, 121, 0, 5, 4, 181, 600),
        (124, 0, 130, 1, 20, 181, 2000),
        (125, 0, 129, 1, 20, 181, 800),
        (126, 50, 0, 1, 20, 181, 100),
    ),
)


#: The Trading Post's currency, in the order it is spent.
#:
#: **Confirmed, from the client.** `UIExchange.ExchangeItemIDs` is a static
#: `int[9]` built by the type's own `.cctor` (ARM64 `0xECE8F0`, which allocates
#: length 9 and initializes it from a metadata blob). The blob is the single
#: nine-integer permutation of the nine Animata item IDs anywhere in the
#: reviewed `global-metadata.dat`, at offset `0x602B01`, and it reads exactly as
#: below: Animata Core first, then the eight older Animata items in ID order.
#: `UIExchange.UpdateOwnCount` labels the counter with the `weeklyItem` holding
#: and files the rest of this array under a parenthesised remainder, which is
#: why the screen reads "86 (+5796)" rather than one total.
#:
#: **Community record, for the spend rule the client does not decide.** The
#: retired service settled a trade, so nothing in the APK states which of these
#: it charged; the same wiki that supplies the rotation states it three times
#: over. Trading Post: 5.5.0 "changed Animata items so that only Animata Core
#: drops from quests. Older items can no longer be obtained, but may still be
#: used in the Trading Post." Animata Core: "If a player still owns older
#: Animata items, they can be used after running out of Animata Core when
#: trading in the Trading Post." Animata Egg: "Unused Animata items are still
#: usable in the Trading Post and will be used after Animata Core." The client's
#: own array order and the record's stated order agree, so the sequence below is
#: sourced twice and guessed nowhere.
#:
#: **Local policy, labeled.** That the nine are interchangeable one for one. No
#: source states a rate, and the counter's plain sum of a holding across all
#: nine is the only arithmetic the client shows for them; a rate would be an
#: invention where the record describes substitutes.
ANIMATA_CURRENCY_IDS: tuple[int, ...] = (181, 124, 125, 126, 127, 128, 129, 130, 131)
