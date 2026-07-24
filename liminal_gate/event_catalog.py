"""Validate local event stages and character grants without bundled game data."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, json
from pathlib import Path

class EventCatalogError(ValueError): pass

@dataclass(frozen=True)
class EventStage:
    event_id: str; flag: str; chapter: int; section: int; stamina: int; coins: int; clear_coins: int; character_ids: tuple[int, ...]

@dataclass(frozen=True)
class EventCatalog:
    stages: tuple[EventStage, ...]
    def by_identity(self): return {(x.chapter, x.section): x for x in self.stages}
    def flags(self): return {x.flag: {"name": x.flag, "value": True} for x in self.stages}

def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load_event_catalog(path: Path, character_catalog_path: Path) -> EventCatalog:
    try:
        doc=json.loads(path.read_text()); chars=json.loads(character_catalog_path.read_text())
    except (OSError,json.JSONDecodeError) as e: raise EventCatalogError("could not read local event or character catalog JSON") from e
    if set(doc) != {"schema_version","provenance","character_catalog_sha256","stages"} or doc["schema_version"] != 1 or doc["provenance"] != "user-supplied": raise EventCatalogError("event catalog has an invalid schema or provenance")
    if doc["character_catalog_sha256"] != _hash(character_catalog_path): raise EventCatalogError("event catalog does not match the local character catalog")
    ids={x.get("character_id") for x in chars.get("characters",[]) if isinstance(x,dict)}
    stages=[]
    for raw in doc["stages"] if isinstance(doc["stages"],list) else []:
        required={"event_id","flag","chapter","section","stamina","coins","clear_coins","character_ids"}
        if not isinstance(raw,dict) or set(raw)!=required: raise EventCatalogError("each event stage has an invalid schema")
        if not isinstance(raw["event_id"],str) or not isinstance(raw["flag"],str) or any(type(raw[x]) is not int or raw[x] < 0 for x in ("chapter","section","stamina","coins","clear_coins")): raise EventCatalogError("event stage has invalid values")
        grants=raw["character_ids"]
        if not isinstance(grants,list) or any(type(x) is not int or x not in ids for x in grants) or grants != sorted(set(grants)): raise EventCatalogError("event grants must be ordered local character IDs")
        stages.append(EventStage(raw["event_id"],raw["flag"],raw["chapter"],raw["section"],raw["stamina"],raw["coins"],raw["clear_coins"],tuple(grants)))
    if not stages or len({(x.chapter,x.section) for x in stages}) != len(stages): raise EventCatalogError("event stages must be nonempty and unique")
    return EventCatalog(tuple(stages))
