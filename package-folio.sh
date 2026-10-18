#!/bin/sh
# Packages a Folio release for PackMan: ./package-folio.sh 48
# takes ../../MuPDF/release-0.0.1-test48/{Folio,FolioSpeech,FolioOCR,FolioCJK}
# -0.0.1-test48.zip and makes Folio_0.0.1.0.48-1.zip and the rest in pool/.
# A zip that isn't in the release is skipped (a plugin left unchanged keeps
# its earlier package). Then run ./publish.sh.
set -eu
cd "$(dirname "$0")"
N=${1:?usage: $0 TEST-NUMBER [UPSTREAM-VERSION]}
UP=${2:-0.0.1}
REL=${REL:-../../MuPDF/release-$UP-test$N}
[ -d "$REL" ] || { echo "No $REL" >&2; exit 1; }
for p in Folio FolioSpeech FolioOCR FolioCJK; do
	z="$REL/$p-$UP-test$N.zip"
	if [ -f "$z" ]; then
		python3 tools/riscpkg.py build "specs/$p" --from "$z" --upstream "$UP" --build "$N"
	else
		echo "($p: no $z, skipped)"
	fi
done
