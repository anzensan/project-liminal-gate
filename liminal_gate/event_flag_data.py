"""How the client names an event flag, and which names are known.

The login and `get_server_status` callbacks pass their `eventFlags` object
straight to `EventManager.SetFlags`, and the client then looks rows up **by
name**. A name the client never asks about is simply inert, so a flag that does
not match the stage it is meant to gate fails silently: the stage never appears
and nothing anywhere says why.

The naming rule is Confirmed from the binary. `CheckQuestFlag` builds its key
with `String.Concat("sp_ch_", id)`, where `id` is either the chapter alone or
`chapter-section`; the chapter-level key acts as a fallback covering every
stage in that chapter. See `reports/7010_native_probe_contract.md` in the
private research tree.

That rule is generative, so the namespace cannot be enumerated: the lists below
are a reference for the *other* flag families, not an allowlist. They are known
to be incomplete -- `sp_matsuno` is a real flag documented in our own reports
and absent from both -- so nothing validates membership against them.
"""

from __future__ import annotations

EVENT_FLAG_PREFIX = "sp_ch_"
DAILY_BONUS_EVENT_FLAG = "enableDailyBonus"
#: The three flags that decide which track the client plays where. Each is a
#: literal in the reviewed 5.5.7 metadata, and each is read the same way every
#: other server flag is -- their metadata-usage shape is indistinguishable from
#: `enableDailyBonus` and `summon_enable`.
TAVERN_BGM_EVENT_FLAG = "use_sakaba_bgm_for_bar"
HUNTING_BGM_EVENT_FLAG = "use_another_bgm_for_hunting"
LIVE_MUSIC_EVENT_FLAG = "EnableLiveMusic"


def event_flags_for(chapter: int, section: int) -> tuple[str, str]:
    """The only two flag names that can gate this stage.

    The first is the chapter-level fallback covering every stage in the
    chapter; the second gates this stage alone.
    """
    return f"{EVENT_FLAG_PREFIX}{chapter}", f"{EVENT_FLAG_PREFIX}{chapter}-{section}"


def daily_bonus_event_flags() -> dict[str, dict[str, object]]:
    """Activate the final client's own recovered 15-day drop rotation.

    The server supplies only the boolean gate.  The surviving client derives
    the bonus kind and eligible chapter from its server-corrected clock, so no
    schedule, multiplier, or battle result is authored here.
    """
    return {
        DAILY_BONUS_EVENT_FLAG: {
            "name": DAILY_BONUS_EVENT_FLAG,
            "value": True,
        },
    }


def music_event_flags() -> dict[str, dict[str, object]]:
    """Reach the tracks the client cannot select on its own.

    Every one of these is audio selection alone: no flag here reaches battle
    settlement, an item, or anything the save records, so none of them is a
    policy an operator needs to choose.  Left unsent they are not silent
    failures in the usual sense -- the client keeps playing whatever the last
    scene started, which reads as a menu whose music simply never changed.

    `use_sakaba_bgm_for_bar` is the Tavern's own theme; without it the menu
    theme carries straight through the Tavern, which is what a tester reported.
    `use_another_bgm_for_hunting` is the Huntland equivalent.  `EnableLiveMusic`
    matters most: the one method that names it also names `BGM100` through
    `BGM103`, so those live-recorded tracks are reachable through this flag and
    nothing else.  Their bundles are in every tester's resource set and the
    client downloads them at startup, so unsent this flag ships five tracks to
    the device that nothing can ever play.

    Two neighbouring flags are deliberately not here. `UseLiveMusicAsDefault`
    and `ReverseTitleMusicOrder` change a default rather than reach otherwise
    unreachable audio, the retired service's value for each is unrecovered, and
    the first shares a method with `EnableSE`, which looks like a local options
    key rather than anything a server ever sent.
    """
    return {
        flag: {"name": flag, "value": True}
        for flag in (
            TAVERN_BGM_EVENT_FLAG,
            HUNTING_BGM_EVENT_FLAG,
            LIVE_MUSIC_EVENT_FLAG,
        )
    }


# Present as literals in the final client's global metadata.
CLIENT_CONFIRMED_EVENT_FLAGS: frozenset[str] = frozenset((
    "EnableFriendInvite",
    "EnableLiveMusic",
    "ReverseTitleMusicOrder",
    "UseLiveMusicAsDefault",
    "achivements_enable",
    "buddy_always_exp_bonus",
    "buddy_same_id_bonus_up",
    "buddy_slot_event_gold_2x",
    "buddy_slot_event_gold_for_10",
    "buddy_slot_event_help_item_present",
    "buddy_slot_event_mticket_present",
    "ch_2004-1-flag1",
    "ch_2004-1-flag2",
    "ch_2004-1-flag3",
    "coop_prize",
    "counter_descent_stamina_one",
    "enableDailyBonus",
    "enableDailyQuest",
    "main_quest_stamina_half",
    "multiplay_enable",
    "multiplay_mainquest_enable",
    "multiplay_stamina_half",
    "multiplay_stamina_zero",
    "slot_event_2_gold_for_10",
    "slot_event_Zup",
    "slot_event_all_plus",
    "slot_event_desc_en",
    "slot_event_desc_ja",
    "slot_event_help_item_present",
    "slot_event_mticket_present",
    "slot_event_ratio_up",
    "summon_enable",
    "tutorial_get_named_healer",
    "use_another_bgm_for_hunting",
    "use_sakaba_bgm_for_bar",
    "vs_friend_enable",
    "vs_normal_enable",
    "vs_stamina_half",
))

# Attested by a community flag table, not client literals. Expected for names
# the client only ever reads back from server data, and not evidence against
# them. See `reports/community_drop_data_assessment.md` privately.
COMMUNITY_ATTESTED_EVENT_FLAGS: frozenset[str] = frozenset((
    "DisableEnterGiftCode_v3_0_0",
    "EnableBuddy",
    "achive-1",
    "achive-2",
    "achive-3",
    "achive-4",
    "achive-5",
    "ch_3002_stamina_half",
    "comeback_campaign_enabled",
    "consecutive_login_campaign_enabled",
    "disableCheckDailyQuestCheat",
    "enableWeeklyChallenge",
    "everydayenergy_enabled",
    "exchange_id1",
    "mp_ch_4000-1",
    "mp_ch_4001-1",
    "mp_ch_4002-1",
    "mp_ch_4003-1",
    "mp_ch_4004-1",
    "mp_ch_4005-1",
    "mp_ch_5000-1",
    "mp_ch_5001-1",
    "mp_ch_5002-1",
    "mp_ch_5003-1",
    "mp_ch_5004-1",
    "mp_ch_5005-1",
    "mp_ch_5500-1",
    "mp_ch_5501-1",
    "mp_ch_5502-1",
    "mp_ch_5503-1",
    "mp_ch_5504-1",
    "mp_ch_5505-1",
    "mp_ch_5999-1",
    "slot_event_ratio_up_2",
    "sp_ch_2000-1",
    "sp_ch_2000-2",
    "sp_ch_2000-3",
    "sp_ch_2001-1",
    "sp_ch_2001-2",
    "sp_ch_2001-3",
    "sp_ch_2002-1",
    "sp_ch_2002-2",
    "sp_ch_2002-3",
    "sp_ch_2003-1",
    "sp_ch_2004-1",
    "sp_ch_2005-1",
    "sp_ch_2006-1",
    "sp_ch_2006-2",
    "sp_ch_2006-3",
    "sp_ch_2008-3",
    "sp_ch_3000-1",
    "sp_ch_3000-11",
    "sp_ch_3000-12",
    "sp_ch_3000-13",
    "sp_ch_3000-14",
    "sp_ch_3000-15",
    "sp_ch_3000-16",
    "sp_ch_3000-2",
    "sp_ch_3000-3",
    "sp_ch_3000-4",
    "sp_ch_3000-5",
    "sp_ch_3000-6",
    "sp_ch_3001-1",
    "sp_ch_3001-2",
    "sp_ch_3002-1",
    "sp_ch_3002-2",
    "sp_ch_3002-3",
    "sp_ch_8001-2",
    "sp_ch_8001-3",
    "sp_ch_8001-4",
    "spring_campaign_enabled",
    "survey-1",
    "vs_enable",
    "vs_honban",
    "vs_stamina_zero",
))

KNOWN_EVENT_FLAGS: frozenset[str] = CLIENT_CONFIRMED_EVENT_FLAGS | COMMUNITY_ATTESTED_EVENT_FLAGS


#: The visibility gate every listed achievement rides.  Recovered from the
#: client's own `AchivementSet`: each `AchivementInfo` carries a `showFlag`, and
#: `AchievementUtil.IsShow` resolves it through `EventManager.GetBoolean`, where
#: an absent key reads false.  Forty-two of the ninety-nine records name this
#: one; the rest name `achive-hide`, which the final client used for the Co-op,
#: VS, Twitter, Line and survey entries whose conditions the retired service
#: owned.
#:
#: Only `achive-1` is sent, and that is a correction rather than the original
#: caution.  `achive-hide` was sent for a while on the reasoning that hiding
#: those entries reproduced a live service's judgement rather than an archive's.
#: A tester's screen settled it: listing them does not cost nothing.
#:
#: Two costs, both in the client and neither reachable from here.  Their
#: `LocalizedString` carries text in `ja` and an empty string in `en` -- the
#: retired service never localised them -- so on an English client roughly
#: twenty of them render as blank rows.  And records 74 through 85 are the only
#: twelve in the whole master whose presents include a `Title`.
#: `AchivementPresent.GetName` resolves a Title through
#: `MultiplayData.instance` with no null guard, inside the window where
#: `UIAchivementItem.isOpenDialog` is true; that static is set once when the
#: claim dialog opens and cleared once when it closes, and `OnClicked` begins
#: `if (isOpenDialog) return`.  So anything that throws in that window kills the
#: claim button for the rest of the process, which is exactly what a tester
#: reported: one claim per app launch, then nothing.
#:
#: Every one of those faults is confined to this set.  All forty-two `achive-1`
#: records are named in English and not one of them pays a Title.  The bundled
#: policy still carries all ninety-eight, because what a record costs to *claim*
#: was never the problem -- what it costs to *show* was.
ACHIEVEMENT_SHOW_FLAGS = ("achive-1",)

#: The main screen's own gate, and a different thing entirely from the show
#: flag above.  That decides which records `UIAchivements` lists once that
#: screen is open; this one decides whether the player can open it at all.
#: `UIMain.Setup` ends with
#: `achievementButton.SetActive(EventManager.GetBoolean("achivements_enable"))`,
#: with `summon_enable` gating its neighbour the same way, so without this flag
#: the button is simply never activated and every achievement behind it is
#: unreachable no matter how complete the list would have been.  Sending the
#: show flags alone furnished a room with no door.
ACHIEVEMENT_MENU_EVENT_FLAG = "achivements_enable"

ACHIEVEMENT_EVENT_FLAGS = (*ACHIEVEMENT_SHOW_FLAGS, ACHIEVEMENT_MENU_EVENT_FLAG)


def achievement_event_flags() -> dict[str, dict[str, object]]:
    """Open the achievements screen and let it list every record.

    Visibility only.  The client holds the whole master -- ids, unlock types,
    thresholds and rewards -- and decides what is unlocked and achieved from
    its own state; these flags are the half the server owns.  Without the show
    flags `UIAchivements` builds an empty list, and without the menu flag
    `UIMain` never activates the button that reaches it.
    """
    return {flag: {"name": flag, "value": True} for flag in ACHIEVEMENT_EVENT_FLAGS}
