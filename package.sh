#!/bin/sh
# Packages every release listed in releases (or just the named packages):
#   ./package.sh            all of them
#   ./package.sh Reel Geany only these
# Each line of releases is
#   <Package> <upstream version> <build> <release zip, relative to RiscOS/>
# Packaging a release that's already in pool/ does nothing, so it's safe to
# run again after updating one line. Then run ./publish.sh.
set -eu
cd "$(dirname "$0")"
ROOT=${ROOT:-../..}
want=" $* "
fail=0
while read -r pkg up build zip; do
	case "$pkg" in ''|\#*) continue;; esac
	if [ $# -gt 0 ]; then
		case "$want" in *" $pkg "*) ;; *) continue;; esac
	fi
	if [ ! -f "specs/$pkg" ]; then echo "$pkg: no specs/$pkg" >&2; fail=1; continue; fi
	if [ ! -f "$ROOT/$zip" ]; then echo "$pkg: no $ROOT/$zip" >&2; fail=1; continue; fi
	python3 tools/riscpkg.py build "specs/$pkg" --from "$ROOT/$zip" \
		--upstream "$up" --build "$build" || fail=1
done < releases
exit $fail
