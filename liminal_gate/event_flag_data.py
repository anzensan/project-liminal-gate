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


# Present as literals in the final client's global metadata.
CLIENT_CONFIRMED_EVENT_FLAGS: frozenset[str] = frozenset((
    "EnableFriendInvite",
    "EnableLiveMusic",
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
