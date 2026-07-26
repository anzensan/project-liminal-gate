# Execution Plans

## Public-release review remediation

Status: completed 2026-07-26.

Objective: fix every issue in the 2026-07-26 full codebase review without
regressing the current client-compatible path.

Required proof:

1. Unknown LAN hosts cannot inherit or mutate the active account, while normal
   signup/login, rotated-token, household, and legacy-save flows still work.
2. Mutation bodies are bounded and incomplete bodies fail explicitly.
3. Save editing clears every durable mutation replay cache when requested and
   validates all party/token shapes the server assumes.
4. Event logs exclude account identifiers and documentation lists their exact
   retained diagnostics.
5. Release gates inspect `build/`, `dist/`, dirty state, and prohibited paths in
   all Git history.
6. The browser editor never inserts user-supplied save values as unescaped
   HTML.
7. Compatibility, distribution, release, checkpoint, and endpoint documents
   agree with current implementation.
8. CI and the full local suite pass with `ResourceWarning` promoted to error.
9. The final diff contains no original material, generated user data, or
   unrelated changes.

Forbidden scope:

- APKs, original resources, raw captures, private account state, and
  `user-data/`.
- New protocol behavior not established by existing evidence.

Result:

- All nine proof items passed.
- The strict full suite passed 287 tests on Python 3.14.6.
- Compile, documentation-link, source preflight, current-history path, and
  clean-candidate repository audit checks passed.
- Ignored local `user-data/` and `build/` contents were neither modified nor
  copied into the clean candidate.
