# What setup generates, and why it keeps each file

Setup works like a compiler: it recovers evidence from your APK, writes
intermediate descriptions that can be inspected and reproduced, then composes the
smaller files used by the client and server. An intermediate can be required to
*build* the complete local game without being required every time the server
runs.

You do not need to read this to install anything. It is here so the generated
output is explainable rather than mysterious, and so a
[dedicated server](dedicated-server.md) operator knows which files to copy.

Everything below stays under the ignored `user-data/` directory.

| Generated output | Why setup creates it | Needed by the running server? |
| --- | --- | --- |
| `il2cpp/DummyDll/` and `il2cpp/dump.cs` | Recover the stripped IL2CPP type layout, game enums, method names, and native offsets from your APK. Later importers cannot safely interpret the master data or native battle code without them. | No. They are retained so catalogs can be inspected or regenerated without rerunning Il2CppDumper. |
| `character-catalog.json` | Records the valid character and job structure recovered from the master data and anchors later catalog provenance to the selected APK. | **Yes.** It authorizes character IDs in the generated archive-event catalog and any explicit override. |
| `derived/native-encounters.json` | Maps the compiled Chapter 8–42 battle programs to the enemies each stage can spawn. Producing it requires the AArch64 disassembler. | No. It is an evidence intermediate used to compose `story-outcomes.json`. |
| `derived/scenario-encounters.json` | Maps the MoonSharp scenario programs used by Chapters 2–7, which have no equivalent compiled battle program. | No. It is another input to `story-outcomes.json`. |
| `story-outcomes.json` | Combines the encounter maps, character catalog, master data, and their hashes into bounded per-stage outcome rules. Without it, the server cannot safely persist a story Companion rolled by the client. | **Yes.** The dedicated server loads this final catalog. |
| `event-catalog.json` | Combines the curated 42-stage Archive, all 12 Tower solo-adapter stages, and the 12 battle/banner-backed solo Eidolon stages with section economics from your BattleData and character associations validated against your character catalog. | **Yes.** It enables 17 Archive chapters, the Tower solo adapter, and solo Eidolon quests; Strikes Back remains bundled. The 16 empty Eidolon tier placeholders are excluded. |
| `companion-equipment.json` | Projects character ancestry, per-job species, and Companion character/species restrictions from the matching APK. It contains no names, skills, descriptions, or assets. `RequiredLevel` is deliberately absent because the final client uses it to activate an equipped Companion's effects, not to prohibit equipping it. | **Yes.** The server needs it to authorize a newly equipped or retargeted Companion; without it, those new links are refused. |
| `resources.json` | Maps every approved resource URL to a local file and hash. | **Yes.** `server_setup` rebuilds or refreshes it from the matching resource tree when the server starts. |
| `public_data/banners/*.png` | Derives the retired Pact banner images from the operator's own resources. | Only if you want those local banner images served. Pact transactions do not depend on them. |
| `public_data/banner_resources/*.bin` | When exact `sp1003` files are absent, derives internally renamed Attack of Coin Creeps card bundles from the retained Coin Creeps-family art. | **Yes for the fallback.** Exact operator-owned `sp1003` resources supersede and remove these generated files. |
| `names.json` | Gives the save editor readable character, item, and Companion names. | No. |
| `input-manifest/` | Records hashes and structural validation for the APK and resource inputs used by this setup. | No. Keep it as provenance evidence. |
| `rehearsal-baseline.json` | Only if you run [the setup rehearsal](setup-rehearsal.md). Records the hashes, counts, and transport result of a run you trusted, so a later run can report exactly what changed. | No. It is derived from your own APK and never leaves your machine. |
| `local-server-plan.json`, the local signing key, and `liminal-gate-test.apk` | Record the client patch, sign it with a local-only key, and produce the APK installed on your device. | The plan and key are not server inputs. The generated APK belongs on the client device. |
| `work/on-device/`, `work/gradle/`, `work/gradle-user-home/`, and `on-device-liminal-gate.apk` | Private staging, pinned build caches, and the combined on-device package. The APK is the installable output; the work directories are reproducible. Deleting workstation build output does not remove an already installed app, but it does not back up that app's private save either. | The package and its full resource tree remain private to the tester. |

Keep the output not marked **Yes** on the setup workstation: it is the
reproducible path from the private APK to the final runtime catalogs, not
unnecessary clutter and not material to publish.

## The local test signing key

The key is created on the first run only. Its password is generated for you and
saved to `user-data/keystore-password.txt` with owner-only permissions, because
that key signs one local test build and its password has to be stored beside it
anyway — choosing one by hand protects nothing. Add `--prompt-key-password` if
you would rather choose it yourself.
