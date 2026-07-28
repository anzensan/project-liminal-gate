# Game Data

The public implementation uses strict, provenance-labeled catalogs for local
story progression, settlements, Hunting, Pacts, Companions, jobs, messages,
Trading Post offers, achievements, and optional events.

Bundled values are either explicitly documented static findings or local
preservation policy. User-derived catalogs stay local and are validated before
server startup. No original master database, protected strings, or extracted
asset content is included here.

Guided setup also projects `companion-equipment.json` from the operator's
matching APK. It retains only character ancestry, each character job's species,
and the Companion character/species restriction fields needed to authorize a
new equipment link. The final-client selection method does not consult
`RequiredLevel`, so the catalog does not contain it.
