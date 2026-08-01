# Changelog

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
