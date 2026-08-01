# Release Scope

## What 1.0 claims

> Every single-player system the retired client had is present, playable, and
> restart-safe, with reward settlement explicitly labeled local preservation
> policy.

That is the whole claim. 1.0 is **not** a fidelity or parity claim: it does not
assert that any reward, rate, or drop matches what the retired service paid out.
Where the service computed a value and the client only rendered it, this project
either labels its own choice as local policy or refuses the outcome. Several
such values are permanently unrecoverable and are recorded as closed questions
in `PARITY_ROADMAP.md`, not as remaining work.

The original client is verified through Chapter 9 by maintainer playthrough on
physical hardware; Chapter 2-1 remains the deepest point backed by preserved
request traces. Everything past Chapter 9 is ordered local progression policy.

## The project

This repository is an unofficial, noncommercial, source-available local
compatibility project. It does not distribute or host an original client,
original game resources, raw traffic captures, private account data, or
credentials.

Included behavior is limited to the operations listed in
`COMPATIBILITY_SCOPE.md` and the capability statuses in
`protocol/endpoint_matrix.yaml`. A listed operation can combine:

- confirmed surviving-client wire behavior;
- static client analysis;
- user-derived local catalogs;
- explicitly labeled local preservation policy.

Those categories are not interchangeable. Passing tests establishes the
documented local implementation and replay/persistence behavior; it does not
establish historical-service fidelity or legal permission to redistribute
original material.

The original client is verified through Chapter 9. Chapter 10 through Chapter 42
is an ordered local progression policy and remains subject to stage-specific
compatibility gaps.

The license is PolyForm Noncommercial 1.0.0. This project is source-available,
not open source. Donations are optional support and confer no access, rights,
features, priority, or service.
