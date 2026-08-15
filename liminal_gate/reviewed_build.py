"""Identity of the one reviewed client build every importer reads.

The profile string is stamped into every derived catalog's provenance, and the
member paths locate the serialized data and the IL2CPP metadata inside the
tester's APK. Importers re-export these under their historical names, so if
the reviewed build is ever re-pinned it changes in exactly one place instead
of drifting across a dozen literals.
"""

from __future__ import annotations

#: The provenance profile every importer writes and every validator checks.
SOURCE_PROFILE = "terra-battle-android-5.5.7-170"
#: The Unity serialized-data bundle the master-data importers read.
APK_DATA_MEMBER = "assets/bin/Data/data.unity3d"
#: The IL2CPP metadata member the dumper and string importers read.
IL2CPP_METADATA_MEMBER = "assets/bin/Data/Managed/Metadata/global-metadata.dat"
#: SHA-256 of the reviewed source APK itself. The on-device route requires it,
#: because that package's literal patch offsets are only correct for these
#: bytes. The emulator route does not, and reads it for one narrower purpose:
#: a file whose digest is this one is certainly the tester's client, so a
#: missing input can be reported as a rename rather than a re-download.
SOURCE_APK_SHA256 = "f2c0ffa188255f4694f0f60e898a58b372c2cc3fff7dd312a01d593189bd7a15"
