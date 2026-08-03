# Publication Checklist

Run this checklist from the independent `project-liminal-gate` repository.

- [ ] `git status --short` is empty.
- [ ] The intended release commit and remote are reviewed.
- [ ] No APK, resource, capture, state, key, password, or user-derived game text
      is tracked or present in the proposed release tree.
- [ ] `android-host/` contains source and pinned wrapper metadata only: no
      wrapper JAR, APK, DEX, native library, Gradle cache, or build output.
- [ ] `python3 -m unittest discover -s tests -v` passes without resource
      warnings.
- [ ] `python3 -m compileall -q liminal_gate tests` passes.
- [ ] `python3 -m liminal_gate.release_preflight` passes.
- [ ] `python3 -m liminal_gate.release_audit` passes.
- [ ] A clean `git archive HEAD` copy passes release preflight.
- [ ] README commands, relative links, compatibility claims, checkpoint, and
      endpoint matrix match the implementation.
- [ ] New mutations have real-HTTP success, denial, retry, collision/body
      identity, restart, and durable-state coverage.
- [ ] On-device claims distinguish source/build, emulator readiness, ABI, and
      physical original-client gameplay evidence; none substitutes for another.
- [ ] New gameplay features are enabled by **both** launchers — guided setup and
      the dedicated server — and named in the setup output. A feature reachable
      only through an explicit `bootstrap_server` flag reaches no operator.
- [ ] `python3 -m liminal_gate.setup_rehearsal` matches its baseline, or its
      differences are understood and accepted.
- [ ] Local policy and recovered behavior remain visibly distinguished.
- [ ] `PROJECT_STATUS.md`, `PLANS.md`, and `docs/current-checkpoint.md` record
      the actual verified boundary and unresolved risks.

Do not publish merely because unit tests are green. Client acceptance and
differential fidelity claims require their separately recorded evidence.
