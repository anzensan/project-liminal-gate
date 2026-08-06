# Contributing

By submitting a contribution, you confirm that you wrote it or have authority
to contribute it. You grant Project Liminal Gate the right to distribute your
contribution under the repository's PolyForm Noncommercial 1.0.0 license.

Do not submit original client binaries, game assets, raw captures, credentials,
extracted data, or material copied from proprietary source code. Contributions
must run using only the public repository and explicitly user-supplied local
data.

## Say what a change costs to deploy

Every changelog entry states which deployment it needs, because the two differ
enormously for the people running this. A server change is a pull and a restart.
A client change means rebuilding the APK, reinstalling it, and — if the signing
key ever differs — re-pointing the save the reinstall orphaned.

- **Server restart** — bundled policies, catalogs, settlement, event flags, and
  anything else the server decides.
- **APK rebuild** — the client patch plan, the compiled server address or port,
  or anything else in `legacy_client_apk_plan.py`.
- **Regenerate the derived catalogs** — a change to one of the *generators*.
  `server_setup` refreshes `resources.json` on start and reads the rest as it
  finds them, so a generator change reaches nobody without this.

Operators are told in [the dedicated-server guide](docs/dedicated-server.md#updating)
that the changelog answers this, so an entry that stays silent leaves them
guessing at exactly the moment it matters.

## Reporting network errors

If a local client-to-server request fails, please open a GitHub **Network
error** issue. Include the exact clean-state setup, commands, client actions,
last route or operation reached, expected result, actual result, and a
sanitized log excerpt. This gives the maintainer a reproducible compatibility
boundary to investigate and fix.

Never attach an APK, asset, raw traffic capture, query string, token, digest,
account state, password, signing key, or other private data. The issue form
includes a checklist and prompts for the required reproduction steps.
