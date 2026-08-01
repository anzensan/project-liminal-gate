# Rehearse setup before you trust a change

Guided setup is the path every operator takes, and the unit suite cannot reach
it: `tests/test_tester_setup.py` proves the decisions setup makes, with the
IL2CPP dump, the master-data import, the catalog derivations, the APK patch, and
the signing all replaced by fakes. Proving the real pipeline still works used to
mean resetting a checkout by hand, running setup, and reading the output.

One command does that now, and compares the result with a run you already
trusted:

```sh
python3 -m liminal_gate.setup_rehearsal \
  --apk /path/to/your/terra-battle.apk \
  --resource-root /path/to/your/resources/data_u2017/android
```

It exits `0` when every compared field matches the baseline and `1` when
anything differs or a stage fails. No emulator, phone, or tablet is involved.

## What it does

1. **Stages a clean source copy.** By default it copies exactly the files Git
   tracks plus the untracked ones it would not ignore — the working tree as it
   stands, including a module you have not committed, and none of the generated
   material beside it. `--revision <rev>` uses a real Git worktree instead,
   which is the stronger claim: the source as published.
2. **Builds an isolated environment** with `venv` and installs the project and
   its `master-import` dependencies into it. `--reuse-venv <dir>` skips this.
3. **Runs the prerequisite check** exactly as `--check` would, and stops on a
   failure with the checklist in `logs/preflight.log`.
4. **Runs guided setup** with `--prepare-only`: a fresh IL2CPP dump, the
   master-data import, the character and Companion-equipment catalogs, the
   native and scenario encounter recovery, the story-outcome and event
   catalogs, the resource inventory, a local signing key, and a patched, signed
   APK. `--reuse-il2cpp <DummyDll>` reuses an existing dump — faster, but it no
   longer proves fresh extraction, and the summary says so.
5. **Serves the generated data to a scripted client.** It starts the server the
   way setup starts it, then runs first-run onboarding over real HTTP: time,
   status, signup, login, userdata, the tutorial Pact, and one hash-checked
   resource. It stops the server, starts it again, and requires the same
   account to load with the granted starter intact and the repeated Pact to
   replay rather than reroll. `--skip-smoke` stops after step 4.

## What it compares

Each run writes `summary.json`, `summary.txt`, and its stage logs into a run
directory under `build/rehearsal/`. The summary holds input hashes,
generated-artifact hashes, catalog row counts, provenance, and the transport
result — and every field in it is compared against the baseline except the ones
that always differ between two correct runs: timestamps, the run directory, the
commit, the interpreter version, and the signed APK (whose hash comes from a
keystore each run creates fresh).

A regression therefore reports itself by name:

```
2 field(s) differ from the baseline:
  artifacts.story-outcomes.json: 4f449bd7... -> 91c2ee01...
  counts.story_rules: 780 -> 604
```

A run takes roughly a minute and keeps about 360 MB — a staged source copy, an
environment, a full set of generated catalogs, and two APKs. Three runs are kept
by default; lower `--keep` if that matters more than the history does.

## The baseline

There is no baseline until you record one, and the first run says so instead of
passing silently:

```sh
python3 -m liminal_gate.setup_rehearsal --apk ... --resource-root ... --update-baseline
```

It is written to `user-data/rehearsal-baseline.json`. **It is never committed**:
every hash in it is derived from your own APK and resource tree. A run refuses
to compare against a baseline recorded from a different APK rather than report
every field as changed.

When a difference is intended — you changed a catalog on purpose — rerun with
`--update-baseline` to accept it.

## Prerequisites

The same ones guided setup needs, because it is guided setup that runs: the
Android SDK build tools, a JDK for `keytool`, `adb`, an AArch64-capable
`objdump`, and Il2CppDumper reachable on `PATH` or named by
`LIMINAL_GATE_IL2CPPDUMPER`. See [Install the tools](install-tools.md). No
device needs to be connected; the device check warns and the rehearsal
continues.

## Options

| Option | What it does |
| --- | --- |
| `--apk`, `--resource-root` | Your own inputs. Both are read-only; nothing writes to them. |
| `--revision <rev>` | Rehearse a committed revision in a worktree instead of the working tree. |
| `--repository <dir>` | The checkout to rehearse. Defaults to the current directory. |
| `--run-root`, `--run-dir` | Where evidence is kept. Defaults to a timestamped directory under `build/rehearsal`. |
| `--keep <n>` | How many previous run directories to keep. Each holds an APK and an environment. Default 3. |
| `--reuse-venv <dir>` | Use an existing environment instead of building one. |
| `--reuse-il2cpp <dir>` | Reuse an Il2CppDumper `DummyDll` directory instead of extracting one. |
| `--skip-smoke` | Generate only; do not start the server. |
| `--build-port <port>` | The port setup bakes into the rehearsed APK. Fixed at 8697 by default so that APK's hash is stable; changing it changes the hash. |
| `--baseline <file>` | Compare against a different baseline. |
| `--update-baseline` | Record this run as the baseline. |

## What it does not cover

The client itself. The rehearsal proves that setup produces the right files and
that the server answers the real onboarding sequence correctly across a
restart; it does not install the APK, and it cannot tell you the app renders.
Certifying a change on a real device is still a device task — see
[Emulator setup](emulator.md) and
[Install on a physical device](device-setup.md).
