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
