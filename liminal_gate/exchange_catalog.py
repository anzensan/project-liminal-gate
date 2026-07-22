"""Strict user-local Trading Post offer catalog."""
from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path
import tomllib

class ExchangeCatalogError(ValueError): pass

@dataclass(frozen=True)
class ExchangeOffer:
    offer_id: int; target_item_id: int; coins: int; target_count: int; initial_count: int; weekly_item_count: int; ingredients: dict[int, int]

@dataclass(frozen=True)
class ExchangeCatalog:
    item_slots: int; max_stack: int; max_coins: int; weekly_item: int; end_date: str; offers: dict[int, ExchangeOffer]

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
    if not isinstance(v,dict) or set(v)!=keys or any(type(v[k]) is not int for k in keys-{'ingredients'}): raise ExchangeCatalogError('offer has an invalid schema')
    if not 1<=v['offer_id'] or not 1<=v['target_item_id']<=slots or v['coins']<0 or v['target_count']<1 or v['initial_count']<1 or v['weekly_item_count']<0 or not isinstance(v['ingredients'],dict): raise ExchangeCatalogError('offer values are outside range')
    ingredients={int(k):n for k,n in v['ingredients'].items() if isinstance(k,str) and k.isdecimal() and 1<=int(k)<=slots and type(n) is int and n>0}
    if len(ingredients)!=len(v['ingredients']): raise ExchangeCatalogError('ingredients require positive in-range decimal IDs')
    return ExchangeOffer(v['offer_id'],v['target_item_id'],v['coins'],v['target_count'],v['initial_count'],v['weekly_item_count'],ingredients)
