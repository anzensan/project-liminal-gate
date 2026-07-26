# Battle System

The surviving client executes battles. This repository does not claim a
clean-room battle simulator or historical enemy-AI reconstruction.

The server's current battle boundary is lifecycle and settlement: it validates
stage identity, entry cost, one active battle, reported result shape, and
catalog-declared reward ceilings before committing durable state. Rejected
settlements leave the active stage and account projection unchanged so the
client can retry honestly.

Canonical original-client acceptance currently ends after Chapter 2-1.
