#!/bin/sh
# Folio is packaged like everything else now: edit its lines in releases
# (Folio's test number; the plugins have their own versions since test55,
# e.g. FolioSpeech-1.0.zip), then run ./package.sh Folio FolioSpeech
# FolioOCR FolioCJK.
set -eu
cd "$(dirname "$0")"
exec ./package.sh Folio FolioSpeech FolioOCR FolioCJK
