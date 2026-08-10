# What setup generates, and why it keeps each file

Setup works like a compiler: it recovers evidence from your APK, writes
intermediate descriptions that can be inspected and reproduced, then composes the
smaller files used by the client and server. An intermediate can be required to
*build* the complete local game without being required every time the server
runs.

You do not need to read this to install anything. It is here so the generated
output is explainable rather than mysterious.

The **Needed by the running server?** column below is a description of the
files, not a packing list. A [dedicated server](dedicated-server.md) derives
every one of them from the APK beside its own resource tree, so there is
nothing to copy between the two machines.

Everything below stays under the ignored `user-data/` directory.

| Generated output | Why setup creates it | Needed by the running server? |
| --- | --- | --- |
| `il2cpp/DummyDll/` and `il2cpp/dump.cs` | Recover the stripped IL2CPP type layout, game enums, method names, and native offsets from your APK. Later importers cannot safely interpret the master data or native battle code without them. | No. They are retained so catalogs can be inspected or regenerated without rerunning Il2CppDumper. |
| `character-catalog.json` | Records the valid character and job structure recovered from the master data and anchors later catalog provenance to the selected APK. | **Yes.** It authorizes character IDs in the generated archive-event catalog and any explicit override. |
| `derived/native-encounters.json` | Maps every compiled battle program the client carries — the core story and the event, side-world, Descent, Tower, Eidolon and Melting Pot chapters alike — to the enemies each stage can spawn. Producing it requires the AArch64 disassembler. | No. It is an evidence intermediate used to compose `story-outcomes.json`. |
| `derived/scenario-encounters.json` | Maps the MoonSharp scenario programs used by Chapters 2–7, which have no equivalent compiled battle program. | No. It is another input to `story-outcomes.json`. |
| `story-outcomes.json` | Combines the encounter maps, character catalog, master data, and their hashes into bounded per-stage outcome rules. Without it, the server cannot safely persist a story Companion rolled by the client. | **Yes.** The dedicated server loads this final catalog. |
| `event-catalog.json` | Combines the curated 42-stage Archive, all 12 Tower solo-adapter stages, and the 12 battle/banner-backed solo Eidolon stages with section economics from your BattleData and character associations validated against your character catalog. | **Yes.** It enables 17 Archive chapters, the Tower solo adapter, and solo Eidolon quests; Strikes Back remains bundled. The 16 empty Eidolon tier placeholders are excluded. |
| `companion-equipment.json` | Projects character ancestry, per-job species, and Companion character/species restrictions from the matching APK. It contains no names, skills, descriptions, or assets. `RequiredLevel` is deliberately absent because the final client uses it to activate an equipped Companion's effects, not to prohibit equipping it. | **Yes.** The server needs it to authorize a newly equipped or retargeted Companion; without it, those new links are refused. |
| `resources.json` | Maps every approved resource URL to a local file and hash. | **Yes.** `server_setup` rebuilds or refreshes it from the matching resource tree when the server starts. |
| `public_data/banners/*.png` | Derives the retired Pact banner images from the operator's own resources. | Only if you want those local banner images served. Pact transactions do not depend on them. |
| `public_data/banner_resources/*.bin` | When exact `sp1003` files are absent, derives internally renamed Attack of Coin Creeps card bundles from the retained Coin Creeps-family art. | **Yes for the fallback.** Exact operator-owned `sp1003` resources supersede and remove these generated files. |
| `drop-compendium.html` | Inverts the drop tables into a readable page: which stages yield a given item or Companion, at the rates the recovered tables state, and which enemy carries each one. Self-contained, so it opens from disk with no server. | No, but the server serves it at `/local/compendium` — see [Reading it in a browser](#reading-the-drop-compendium-in-a-browser). |
| `names.json` | Gives the save editor readable character, item, and Companion names. | No. |
| `tuning.toml` | Collects the rates, availability schedules, party gates, and EXP multiplier this project chose rather than recovered, with every option documented and commented out. Written once and never overwritten, so your edits survive a setup rerun. | Only if you change something. Every line left commented keeps following its bundled default, so a fresh file behaves exactly like no file. Deleting it is safe; the next run writes a new copy. |
| `input-manifest/` | Records hashes and structural validation for the APK and resource inputs used by this setup. | No. Keep it as provenance evidence. |
| `rehearsal-baseline.json` | Only if you run [the setup rehearsal](setup-rehearsal.md). Records the hashes, counts, and transport result of a run you trusted, so a later run can report exactly what changed. | No. It is derived from your own APK and never leaves your machine. |
| `local-server-plan.json`, the local signing key, and `liminal-gate-test.apk` | Record the client patch, sign it with a local-only key, and produce the APK installed on your device. | The plan and key are not server inputs. The generated APK belongs on the client device. |
| `work/on-device/`, `work/gradle/`, `work/gradle-user-home/`, and `on-device-liminal-gate.apk` | Private staging, pinned build caches, and the combined on-device package. The APK is the installable output; the work directories are reproducible. Deleting workstation build output does not remove an already installed app, but it does not back up that app's private save either. | The package and its full resource tree remain private to the tester. |
| `on-device-state/` | Saves exported off an Android install by [`on_device_state`](saves.md#the-on-device-save). Each file is a full save, written once and never rotated or pruned. | No. This is the only copy of that progress that exists outside the device, so it is the one directory here you should not delete. Treat each file as privately as the save itself. |

Keep the output not marked **Yes** on the setup workstation: it is the
reproducible path from the private APK to the final runtime catalogs, not
unnecessary clutter and not material to publish.

## Reading the drop compendium in a browser

The page is a plain file, so the simplest way to read it is to open
`user-data/drop-compendium.html` directly. The server also serves it, which is
what the on-device package needs — there the phone is the only machine involved
and has no file manager pointed at `user-data/`.

Anyone the server already serves the game to can read it. That is the same
network and the same audience: the page is derived from the very APK those
clients are running, so withholding a reference to a game while serving the game
itself would draw a line nothing rests on. It stays read-only, and it reaches
nothing that network cannot already ask this server for.

The save and the event log are **not** like this. Both stay loopback-only, and
one of them is writable — they describe a person, where this describes the game.

| Where you are | Open |
| --- | --- |
| On the phone running the all-in-one package | `http://127.0.0.1:8002/local/compendium` |
| On the machine running a dedicated server | `http://127.0.0.1:PORT/local/compendium`, with the port that host serves on |
| On a phone or laptop served by a dedicated server | `http://SERVER_LAN_ADDRESS:PORT/local/compendium` — the same address the client is pointed at |
| Not on that network at all | Nothing. Copy the file instead — it needs no server. |

The all-in-one package is the exception, and by binding rather than by rule: its
server listens on loopback, so nothing on your network can reach that copy.

Two things to get right, because each fails in a way that does not name itself:

- **`http://`, not `https://`.** The server speaks plain HTTP and has no
  certificate, so a browser told to negotiate TLS reports *"This site can't
  provide a secure connection"* rather than anything about the route. Type the
  scheme rather than letting the address bar guess it.
- **A JSON `no_local_drop_compendium` reply means the page is genuinely
  missing**, not that the address is wrong. On a dedicated host, start it once
  more and read what it prints about the compendium; on the on-device package,
  the build predates the page and needs an APK rebuild.

## The local test signing key

The key is created on the first run only. Its password is generated for you and
saved to `user-data/keystore-password.txt` with owner-only permissions, because
that key signs one local test build and its password has to be stored beside it
anyway — choosing one by hand protects nothing. Add `--prompt-key-password` if
you would rather choose it yourself.
