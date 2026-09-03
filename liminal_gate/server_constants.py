"""The `constants` object the final client reads from the server-status route.

The client does not merely display these values -- several of its screens are
*gated* on them, and one of those gates is why Huntland looked permanently
locked while the server-side policy was already enabled:

- `UIIconBtn.Update` (ARM64 `0xE942B8-0xE94314`) disables all four Huntland
  cards unless `UserData.IsFinalMajorUpdated()` is true, and that predicate
  (`0x19D75D4-0x19D7680`) requires both `currentVersion_iOS` and
  `currentVersion_Android` to exceed `4.99`.  This is independent of story
  progress, event flags, and `metalZoneUnlockTime`.
- `UISpecialSelect` mode 6 reads `metalHuntingList` and mode 7 reads
  `huntingHuntingList`.  The final APK hard-codes no per-zone thresholds, so
  the server is the only authority for which zones exist.

Two consequences shape this module.  The block is served whole rather than in
part, because the client's setter indexes the opening economy keys directly.
And the country arrays are not optional once the version gate passes: the same
final-major branch in `UITitle.<_Login>.MoveNext` (`0xF411C4`) dereferences
`CountryCodes` and `NoServiceCountryCodes` immediately, and reaches
`ShowSelectUserCountry` -- which consumes `CountriesJa` or `CountriesEn` -- when
no country is stored.  Supplying the version without the arrays turns a locked
card into a title-login `NullReferenceException`.

Recovered values are labeled Confirmed in `docs/findings.md`.  The country
roster is not recovered and is an explicitly local compatibility fixture.
"""

from __future__ import annotations

from typing import Any

from liminal_gate.archive_economy import DAILY_QUEST_FREE_ENERGY
from liminal_gate.luck_data import (
    COMPANION_LUCK_GAIN_BOOST,
    COMPANION_PERSONAL_LUCK_TENTHS,
    COMPANION_TEAM_LUCK_TENTHS,
)
from liminal_gate.save_validation import MAX_ITEM_STACK
from liminal_gate.secondary_world_data import world_max_chapters
from liminal_gate.story_progression_catalog import CORE_SECTION_COUNTS


# The final archive client is 5.5.7, so the final-major state is advertised
# explicitly rather than inferred.
FINAL_CLIENT_VERSION = 5.57
# The retired service's country roster was not recovered.  One aligned local
# projection keeps established accounts out of the country-selection flow; it is
# not a claim about the original service's data.
LOCAL_COUNTRY_CODE = "US"
LOCAL_COUNTRY_NAME = "United States"
# Normal Special mode falls back to UISpecialSelect's fixed 50-entry list when
# this server list is empty. That fallback contains all Chapter 3000 Metal
# rows, so a Metal visibility flag makes them leak into Arena -> Special
# Quests. 3003-1 is a recovered entry in that fixed list; without its event
# flag it remains closed, while its presence keeps the client from taking the
# fallback. A configured local event catalog replaces this one-entry fixture.
CLOSED_SPECIAL_QUEST_SENTINEL = "3003-1"


def _by_companion_id(effects: dict[int, int]) -> dict[str, int]:
    """A Companion effect table in the string-keyed form the client parses.

    `SetServerConstants` stores these three as `JsonData` and every read of one
    looks the Companion up by `buddyID.ToString()`, so an integer key is a key
    the client never finds.
    """
    return {str(companion): effect for companion, effect in effects.items()}


# The last core-story chapter, taken from the same table the progression graph
# is built from so the ceiling below can never fall behind the story it bounds.
LAST_CORE_STORY_CHAPTER = max(CORE_SECTION_COUNTS)

# Every name `UserData.SetServerConstants` (`0x19D2A74`-`0x19D6904`) looks up in
# this block, in the order its literals appear.  A key outside this set is not
# rejected by the client, it is *ignored* -- the setter reads a fixed list and
# never walks the object -- so sending one is silent and leaves the field at its
# `UserData..cctor` default.  That is how `maxBuddyBoxCount`, the name of the
# static rather than the name of the key, held every account's Companion box at
# 250 while this module said 1000.  `patchVersion` is an object and the two keys
# inside it, `appVersion` and `timestamp`, are not top-level names.
CLIENT_CONSTANT_KEYS = frozenset({
    "minStamina", "maxStamina", "maxChapter", "maxCoins", "maxEnergy",
    "maxFreeEnergy", "maxItemCount", "refillInterval", "refillCost",
    "maxMessages", "levelCap", "NormalSlotCoins", "RareSlotEnergy",
    "AddJobEnergy", "vsStaminaRefillInterval", "maxVsStamina", "helpURL_jp",
    "helpURL_en", "privacyPolicy_ja", "privacyPolicy_en", "tosURL_jp",
    "tosURL_en", "creditsURL", "supportURL_jp", "supportURL_en",
    "supportEmail_jp", "supportEmail_en", "ChapterClearEnergyBonus",
    "EnergyBonusByDailyQuest", "NormalBuddySlotCoins", "RareBuddySlotEnergy",
    "supportURL_fr", "supportURL_de", "supportURL_es", "supportEmail_fr",
    "supportEmail_de", "supportEmail_es", "supportURL_zh", "supportEmail_zh",
    "scheduleURL_jp", "scheduleURL_en", "supportURL_AndApp",
    "supportURL_AppStore", "supportURL_GooglePlay",
    "andapp_refundable_end_datetime", "appstore_refundable_end_datetime",
    "googleplay_refundable_end_datetime", "luckUpBuddies", "teamLuckUpBuddies",
    "luckUpBoostBuddies", "statusUpItems", "specialQuestList",
    "descentQuestList", "eidolonQuestList", "towerQuestList",
    "metalHuntingList", "huntingHuntingList", "descentHuntingList",
    "helpItemEnabled", "changeUsernameEnabled", "currentVersion_iOS",
    "currentVersion_Android", "patchVersion", "BuddyBoxMax",
    "SameBuddyExpBonus", "LuckyLuckBonus", "MaxStaminaBias",
    "VsMatchInterval1", "VsMatchInterval2", "patchDataZipped",
    "CampaignSlotEnergy", "CampaignBuddySlotEnergy",
    "SameBuddyExpBonus_InCampaign", "purchasePaidEnergyCount",
    "purchaseFreeEnergyCount", "worldMaxChapter", "AdMovieFreeEnergy",
    "AdSuppressionPeriod", "CountriesJa", "CountriesEn", "CountryCodes",
    "NoServiceCountryCodes",
})


def build_server_constants(
    normal_slot_coins: int | None = None, rare_slot_energy: int | None = None,
    *, secondary_worlds: bool = False,
) -> dict[str, Any]:
    """Return the client-facing constants block, without the Huntland lists.

    The two zone lists are account-aware and are added by the caller, which
    knows the account's story progress; everything here is the same for every
    local account.

    The two Pact costs are parameters because sending them makes the client
    enforce them, and a value that disagrees with what the active local Pact
    policy actually charges is worse than sending nothing: the client would
    refuse a draw the server would have allowed, or offer one it then refuses.
    The caller passes the running policy's own costs, so one number governs
    both the client's gate and the server's charge.
    """
    constants: dict[str, Any] = {
        "currentVersion_iOS": FINAL_CLIENT_VERSION,
        "currentVersion_Android": FINAL_CLIENT_VERSION,
        "CountriesJa": [LOCAL_COUNTRY_NAME],
        "CountriesEn": [LOCAL_COUNTRY_NAME],
        "CountryCodes": [LOCAL_COUNTRY_CODE],
        "NoServiceCountryCodes": [],
        "specialQuestList": [CLOSED_SPECIAL_QUEST_SENTINEL],
        "minStamina": 1,
        "maxStamina": 100,
        # `worldMaxChapter` is the sibling of this key and is added below, but
        # only while the secondary worlds are served. It is a ceiling per world
        # and `UserData.get_worldChapterNo` clamps against it, so sending it
        # with no world to enter would declare a shape the player cannot reach.
        #
        # `WORLD_NUM` is *not* sent, and its absence is not an omission. It
        # reads like a server constant -- `public static int WORLD_NUM` sits at
        # 0x200 beside `worldMaxChapter` at 0x1F8 -- but the build carries no
        # such string literal and `SetServerConstants` never looks for one.
        # `UserData..cctor` assigns it the literal 3, which is the length
        # `InitData` then allocates `worldProgressCode` at. There is nothing
        # here for a server to declare.
        #
        # The last core-story chapter, and a ceiling the client applies to the
        # *player* rather than to the catalogue.  `UserData.get_chapterNo`
        # (ARM64 `0x19D752C`-`0x19D75D0`) does not return the stored chapter: it
        # returns `min(_chapterNo, maxChapter)`, and `get_sectionNo`
        # (`0x19D7B58`) answers the sentinel 100 -- "this chapter is finished"
        # -- whenever the stored chapter is the larger of the two.  Everything
        # the player sees reads the clamped pair: `UIMap.getCurrentChapter`
        # reaches it through `UserData.get_worldChapterNo` (`0x19D7938`), which
        # tail-calls the clamp for world 0, and so do `UnlockNextChapter` and
        # `UnlockNextSection`.
        #
        # So a value below the story's own length does not shorten the map, it
        # strands the account at the ceiling.  This module sent 40 while
        # BattleData carries Chapters 1--42, which is issue 82: a player who
        # cleared 40-10 had `_chapterNo` advanced to 41 by a clear the server
        # accepted and recorded, and then read it back as chapter 40 section
        # 100.  The clear registered, Chapter 41 never opened, and no request
        # failed -- the ceiling is applied entirely inside the client.
        #
        # 42 is the largest core-story chapter in the reviewed client's own
        # BattleData, so the clamp now does only the job it exists for: an
        # account that finishes 42-3 is written forward to 43-1 and reads back
        # as Chapter 42, fully cleared, standing on the last map the client
        # draws.
        "maxChapter": LAST_CORE_STORY_CHAPTER,
        "maxCoins": 99999999,
        "maxEnergy": 9999,
        "maxFreeEnergy": 9999,
        # The client enforces this ceiling on its own inventory, and every
        # server-side item projection is compared against what the client then
        # reports, so the two have to be one number rather than two literals.
        "maxItemCount": MAX_ITEM_STACK,
        "refillInterval": 120,
        "refillCost": 1,
        "maxMessages": 100,
        "levelCap": 90,
        # Defaults matching the bundled Pact policy; see the docstring. 5 is the
        # cost the service charged for a single Truth pull. The client falls
        # back to 3 when this key is absent, which is why a local capture taken
        # before this block was sent recorded the wrong number.
        "NormalSlotCoins": 3000,
        "RareSlotEnergy": 5,
        "AddJobEnergy": 3,
        "vsStaminaRefillInterval": 300,
        "maxVsStamina": 5,
        # The retired help, policy, terms, support, and credits pages are gone.
        # Empty strings leave the client's own embedded defaults in place rather
        # than pointing a tester at a dead or substituted address.
        "helpURL_jp": "",
        "helpURL_en": "",
        "privacyPolicy_ja": "",
        "privacyPolicy_en": "",
        "tosURL_jp": "",
        "tosURL_en": "",
        "creditsURL": "",
        "supportURL_jp": "",
        "supportURL_en": "",
        "supportEmail_jp": "",
        "supportEmail_en": "",
        "ChapterClearEnergyBonus": 1,
        # The client draws the Daily Quest result screen's Energy reward from
        # this key and takes the balance from the clear response, so the two
        # come from one number; see `archive_economy.DAILY_QUEST_FREE_ENERGY`.
        "EnergyBonusByDailyQuest": DAILY_QUEST_FREE_ENERGY,
        # The pre-battle Power-Up Item slot is gated on this one flag and
        # nothing else the account owns.  `UITeamPopup.<Setup>` caches
        # `IsHelpItemEnabled()` (ARM64 `0xD65A08`), which returns false unless
        # `UserData.helpItemEnabled` -- this key, at static offset `0x1F0` -- is
        # true, so an absent key hid the whole row even for a player holding
        # Disarmers.  The other two terms are the client's own: the slot stays
        # hidden inside the tutorial and on World-0 map specials.
        "helpItemEnabled": True,
        # No character-box key is sent, and that is not an omission.
        # `SetServerConstants` reads a fixed list of names and none of them
        # names the character box, so `maxCharacterCount` -- the static at
        # offset 0x68 -- keeps whatever `UserData..cctor` gave it, which is
        # 0x400 = 1024 (`0x19DE2B4`). A `maxCharacterCount` key was sent here
        # until 2026-08-17 and was read by nothing; the roster ceiling the
        # client actually applies has always been its own 1024.
        # The Companions of Fellowship pull price. The client displays
        # whatever this says, so it is policy rather than recovery; 2,000
        # is the figure the Companions of Fellowship page records, and it
        # must stay equal to `BUNDLED_COIN_COST`, which the draw route
        # charges. A tester paid 3,000 here until 2026-08-18.
        "NormalBuddySlotCoins": 2000,
        "RareBuddySlotEnergy": 3,
        # The Companion box, and the key name is the client's rather than the
        # field's: `SetServerConstants` looks up `BuddyBoxMax` (`0x19D53F4`)
        # and stores it into the static named `maxBuddyBoxCount` at offset
        # 0x74. Sending the field name instead left the box at the client's own
        # `..cctor` default of 250 (`mov w13, #0xfa` at `0x19DE2C4`), which is
        # the ceiling a tester hit while the server had already been settling
        # drops against 1000 -- and the client, holding the smaller number,
        # refused to enter any stage that could drop a Companion.
        "BuddyBoxMax": 1000,
        # Final production retained the ordinary 2x matching-Companion bonus.
        "SameBuddyExpBonus": 2,
        "SameBuddyExpBonus_InCampaign": 2,
        # Companion master Luck effects, stored in Luck tenths, recovered from
        # the final client's embedded Character Luck dictionaries.  The client's
        # Companion/Luck properties require these three to be present.
        #
        # They are projected from `luck_data` rather than restated here,
        # because the chest roll averages the party's Luck with these same
        # effects applied.  Two copies could disagree, and the disagreement
        # would be invisible: the client would show the team Luck it was told
        # while the server rolled the chests against a different number.
        "luckUpBuddies": _by_companion_id(COMPANION_PERSONAL_LUCK_TENTHS),
        "teamLuckUpBuddies": _by_companion_id(COMPANION_TEAM_LUCK_TENTHS),
        # Royal Ringstone doubles a successful per-character Luck increment.
        "luckUpBoostBuddies": _by_companion_id(COMPANION_LUCK_GAIN_BOOST),
    }
    if normal_slot_coins is not None:
        constants["NormalSlotCoins"] = normal_slot_coins
    if rare_slot_energy is not None:
        constants["RareSlotEnergy"] = rare_slot_energy
    if secondary_worlds:
        # An array indexed by world, carrying internal chapter numbers, which
        # `get_worldChapterNo` clamps a world's own chapter against. Sent as a
        # JSON array because that is what `SetServerConstants` reads: it walks
        # `0..Count` with the integer `get_Item`, unlike `worldProgressCode`,
        # whose keys it parses as strings.
        #
        # The client rewrites index 2 to 114 itself unless `sp_five_emperors2`
        # is set, which is how the five hard descents stay shut behind their own
        # flag. Nothing here needs to reproduce that; sending the full ceiling
        # and the flag together is what opens them.
        constants["worldMaxChapter"] = world_max_chapters()
    return constants


# The country the client stores for a local account, returned alongside login so
# the stored value and `CountryCodes[country_id]` agree.
LOCAL_LOGIN_COUNTRY_FIELDS = {"country_id": 0, "countryCode": LOCAL_COUNTRY_CODE}
