"""Strict user-local Trading Post offer catalog."""
from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path
import tomllib

from liminal_gate.trading_post_data import TRADING_POST_WEEKS

class ExchangeCatalogError(ValueError): pass

@dataclass(frozen=True)
class ExchangeOffer:
    offer_id: int; target_item_id: int; coins: int; target_count: int; initial_count: int; weekly_item_count: int; ingredients: dict[int, int]
    # Exactly one target is set; the client reads whichever ID is nonzero.
    target_buddy_id: int = 0

@dataclass(frozen=True)
class ExchangeCatalog:
    item_slots: int; max_stack: int; max_coins: int; weekly_item: int; end_date: str; offers: dict[int, ExchangeOffer]
    # Companion box ceiling, needed only by offers that award a Companion.
    max_owned: int = 1000
    # Offer IDs per week of the rotation. A single-entry tuple means the whole
    # catalog is always open, which is how an operator catalog behaves.
    weeks: tuple[tuple[int, ...], ...] = ()

    def week_count(self) -> int:
        return len(self.weeks) or 1

    def offers_open_at(self, week_index: int) -> dict[int, ExchangeOffer]:
        """The offers a player can see and trade during one week."""
        if not self.weeks:
            return self.offers
        return {i: self.offers[i] for i in self.weeks[week_index % len(self.weeks)]}

def load_exchange_catalog(path: Path) -> ExchangeCatalog:
    try: d = tomllib.loads(path.read_text()) if path.suffix.lower()=='.toml' else json.loads(path.read_text())
    except (OSError,json.JSONDecodeError,tomllib.TOMLDecodeError) as e: raise ExchangeCatalogError('could not read Trading Post catalog JSON or TOML') from e
    required={'schema_version','provenance','item_slots','max_stack','max_coins','weekly_item','end_date','offers'}
    if not isinstance(d,dict) or set(d)!=required or d['schema_version']!=1 or d['provenance']!='user-supplied': raise ExchangeCatalogError('Trading Post catalog has an invalid schema')
    if any(type(d[k]) is not int or d[k]<1 for k in ('item_slots','max_stack','max_coins')) or type(d['weekly_item']) is not int or d['weekly_item']<0 or not isinstance(d['end_date'],str) or not isinstance(d['offers'],list): raise ExchangeCatalogError('Trading Post catalog values are invalid')
    offers=tuple(_offer(x,d['item_slots']) for x in d['offers']); ids=[x.offer_id for x in offers]
    if ids!=sorted(ids) or len(ids)!=len(set(ids)): raise ExchangeCatalogError('offers must be ordered and unique')
    return ExchangeCatalog(d['item_slots'],d['max_stack'],d['max_coins'],d['weekly_item'],d['end_date'],{x.offer_id:x for x in offers})

def _offer(v: object, slots:int)->ExchangeOffer:
    keys={'offer_id','target_item_id','coins','target_count','initial_count','weekly_item_count','ingredients'}
    optional={'target_buddy_id'}
    if not isinstance(v,dict) or not keys<=set(v) or set(v)-keys-optional or any(type(v[k]) is not int for k in keys-{'ingredients'}): raise ExchangeCatalogError('offer has an invalid schema')
    buddy=v.get('target_buddy_id',0)
    if type(buddy) is not int or buddy<0: raise ExchangeCatalogError('target_buddy_id must be a nonnegative integer')
    # An offer awards an item or a Companion, never both and never neither.
    if bool(v['target_item_id'])==bool(buddy): raise ExchangeCatalogError('each offer must award exactly one of target_item_id or target_buddy_id')
    if not 1<=v['offer_id'] or v['target_item_id'] and not 1<=v['target_item_id']<=slots or v['coins']<0 or v['target_count']<1 or v['initial_count']<1 or v['weekly_item_count']<0 or not isinstance(v['ingredients'],dict): raise ExchangeCatalogError('offer values are outside range')
    ingredients={int(k):n for k,n in v['ingredients'].items() if isinstance(k,str) and k.isdecimal() and 1<=int(k)<=slots and type(n) is int and n>0}
    if len(ingredients)!=len(v['ingredients']): raise ExchangeCatalogError('ingredients require positive in-range decimal IDs')
    return ExchangeOffer(v['offer_id'],v['target_item_id'],v['coins'],v['target_count'],v['initial_count'],v['weekly_item_count'],ingredients,buddy)


BUNDLED_ITEM_SLOTS = 181
BUNDLED_MAX_STACK = 999
BUNDLED_MAX_COINS = 99999999
BUNDLED_MAX_OWNED = 1000


# The rotation turned over every Friday at 00:00 UTC.  The anchor below is
# Friday 2018-10-05 00:00 UTC, the rotation week during which version 5.5.0
# shipped the fixed cycle (2018-10-10 00:00 UTC, per the archived official
# news post) with the first table's offers live.  The wiki's rotation page was
# then built live, one table per Friday -- eight dated "Added trade" edits,
# 2018-10-12 through 2018-11-23, closing with "Rotation finished" on Friday
# 2018-11-30 when the cycle looped back to the first table.  That dated edit
# trail is what fixes the phase; see `trading_post_data` for the citations.
_ROTATION_EPOCH = 1_538_697_600
_WEEK_SECONDS = 604800


def active_week_index(now: float, week_count: int) -> int:
    """Which week of the rotation is open at a moment in time.

    The turnover cadence is the wiki's: every Friday at 00:00 UTC.  The phase
    is anchored so that week 0 -- the first bundled table -- is open on the
    same real-world weeks it historically was, dated by the rotation page's
    own edit history (community record, not a service capture).  Moments
    before the anchor extend the same cycle backward, which is deterministic
    even though the fixed rotation did not exist before version 5.5.0.
    """
    return int((now - _ROTATION_EPOCH) // _WEEK_SECONDS) % max(week_count, 1)


def build_bundled_exchange_policy() -> ExchangeCatalog:
    """Return the guided-path local Trading Post policy."""
    offers: dict[int, ExchangeOffer] = {}
    weeks: list[tuple[int, ...]] = []
    costs: set[int] = set()
    for week in TRADING_POST_WEEKS:
        for offer_id, target_item, target_buddy, target_count, stock, cost_item, cost_count in week:
            offers[offer_id] = ExchangeOffer(offer_id, target_item, 0, target_count, stock, 0,
                                             {cost_item: cost_count}, target_buddy)
            costs.add(cost_item)
        weeks.append(tuple(row[0] for row in week))
    # `UIExchange.UpdateOwnCount` labels the screen with how many of
    # `weeklyItem` you hold, and counts every *other* currency in its static
    # `ExchangeItemIDs` as a parenthesised remainder. Sending 0 named no item,
    # so a player holding 249 Animata Cores read "0 (+249)" at a counter that
    # only ever charges Animata Cores. The recovered rotation prices every one
    # of its offers in a single item, so name it rather than hard-code it.
    weekly_item = costs.pop() if len(costs) == 1 else 0
    return ExchangeCatalog(BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK, BUNDLED_MAX_COINS, weekly_item, "",
                           offers, BUNDLED_MAX_OWNED, tuple(weeks))
