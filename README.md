# riscos-packages

PackMan packages of RISC OS ports and applications by Andrew Youll.

## Using them

In PackMan, choose **Sources…** from the icon bar menu, add

    https://adyoull.github.io/riscos-packages/pkg/index

and choose **Update lists**. The packages then show in PackMan alongside
the others. The list is also on <https://adyoull.github.io/riscos-packages/>.

| Package | Version | What it is |
|---|---|---|
| AbiWord | 3.0.8.0.3-1 | AbiWord word processor (GTK 3) |
| AddrSpace | 0.1.0.0.1-1 | Shows what is using RISC OS's logical address space |
| ClawsMail | 4.4.0.0.24-1 | Claws Mail email client (GTK 3) |
| FFmpeg | 5.1.10.0.23-1 | FFmpeg 5.1 LTS (ffmpeg, ffprobe, ffplay) for ARMv7 NEON |
| fheroes2 | 1.1.17.0.5-1 | Free re-creation of the Heroes of Might and Magic II engine |
| Folio | 0.0.1.0.71-1 | Reader for PDF and ebook files, built on MuPDF |
| FolioCJK | 1.0.0.1-1 | Chinese, Japanese and Korean font for Folio |
| FolioOCR | 1.0.0.1-1 | Text recognition (OCR) for Folio, English |
| FolioSpeech | 1.0.0.1-1 | Reading aloud for Folio (British English voice) |
| Freeciv | 3.2.6.0.14-1 | Civilization-style turn-based strategy game (Freeciv 3.2.6) |
| Geany | 2.1.0.12-1 | Geany programmer's editor (GTK 3) |
| Gnumeric | 1.12.57.0.17-1 | Gnumeric spreadsheet (GTK 3) |
| GOGImport | 1.0.0.1-1 | Gets Heroes III's files out of the GOG installer for VCMI |
| Julius | 1.8.0.0.1-1 | Open-source engine for Caesar III, the Roman city-building game |
| L3afpad | 0.8.18.1.11.0.33-1 | L3afpad simple text editor (GTK 3) |
| Matinee | 0.1.1.0.1-1 | Plex, Jellyfin and DLNA media client with a built-in player |
| mtPaint | 3.50.14.0.12-1 | mtPaint painting program (GTK 3) |
| NetStats | 1.06.0.1-1 | Network statistics: traffic graphs, connections and LAN devices |
| OpenTTD | 14.1.0.7-1 | Open-source transport simulation game (OpenTTD 14.1) |
| OpenTTD-OpenMSX | 14.1.0.7-1 | Music for OpenTTD (OpenMSX) |
| OpenTTD-OpenSFX | 14.1.0.7-1 | Sound effects for OpenTTD (OpenSFX) |
| PCSX | 26.0.2-1 | PlayStation emulator (PCSX ReARMed) |
| PDFS | 0.14~beta.0.1-1 | Phones, tablets and cameras (MTP) as discs |
| PThreadTicker | 0.03.0.1-1 | Keeps threaded UnixLib programs safe in the desktop |
| RDPServer | 0.2.0.1-1 | Remote Desktop (RDP) server for the RISC OS desktop |
| Reel | 0.1.29.0.1-1 | Video player for the RISC OS desktop, built on FFmpeg |
| ReelEdit | 0.3~beta.0.1-1 | Non-linear video editor, built on MLT and FFmpeg |
| SoftMIDI | 0.5.0.0.1-1 | General MIDI SoundFont and the *MIDIPlay player |
| TORCS | 1.3.7.0.4-1 | The Open Racing Car Simulator, a 3D racing game |
| TORCS-Tracks | 1.3.7.0.3-1 | All 29 extra tracks for TORCS |
| TORCS-Tracks-DirtOval | 1.3.7.0.3-1 | Dirt and oval tracks for TORCS |
| TORCS-Tracks-Road1 | 1.3.7.0.3-1 | Road tracks for TORCS (E-Track 2, Ole Road 1, E-Track 6) |
| TORCS-Tracks-Road2 | 1.3.7.0.3-1 | Road tracks for TORCS (Brondehach, Wheel 1 and 2, Alpine 2) |
| TORCS-Tracks-Road3 | 1.3.7.0.3-1 | Road tracks for TORCS (Corkscrew, E-Track 3 and seven more) |
| TTF-Noto-Color-Emoji | 2.051.0.1-1 | Noto Color Emoji font for fontconfig programs |
| TubeSearch | 0.2.0~rc14.0.1-1 | Search and browse YouTube, and play videos in Reel |
| VCMI | 1.7.5.0.2-1 | Open-source engine for Heroes of Might and Magic III |
| Warzone2100 | 2.3.9.0.14-1 | Real-time strategy game (Warzone 2100 2.3.9) |
| YSFlight | 0.0.1-1 | Free flight simulator (YSFlight Community Edition) |

## Version numbers

Every package version is

    <upstream version>.0.<build>-<package revision>

* **upstream version**: the program's own version (for a port, the
  upstream release it was built from), unchanged;
* **.0.<build>**: our build of that version, counting from 1. The `.0.`
  keeps our builds after the upstream release they come from and before
  the next upstream point release, so they never take one of its numbers
  (ffmpeg 7.1 < 7.1.0.3 < 7.1.1);
* **-<revision>**: the package revision, from 1, raised only when the same
  build is packaged again (a fix to the package's details, not the program).

A release keeps its `.0.<build>`; it is never the bare upstream version,
which would sort below its own test builds. Folio 0.0.1-test48 is
`0.0.1.0.48-1`.

## How it works

The release zips are made by each program's own tools, with RISC OS
filetypes in the zip. `tools/riscpkg.py` repackages them:

* `specs/<Package>` is the package's control record (as in RiscPkg/Control,
  without the version) plus `Build-` fields saying which part of the
  release zip goes where in the package, and which files make up
  RiscPkg/Copyright.
* `riscpkg.py build SPEC --from RELEASE.zip --upstream 0.0.1 --build 48`
  makes `pool/<Package>_<version>.zip` and checks it: the fields the
  RiscPkg policy needs, the section, the version (it must go up), the
  dependencies, the components, and a RISC OS filetype on every file.
  Packaging the same build again gives the same package, or the next
  revision if the contents changed.
* `riscpkg.py index` makes `site/`: the newest package of each name, the
  PackMan index `pkg/index` (each package's control record plus Size,
  MD5Sum and URL), `pointer` (the packages' URLs) and `index.html`.
* `publish.sh` pushes this branch (tools and specs) to `main` and `site/`
  as a single commit to `gh-pages`, which GitHub Pages serves. Old
  package zips stay in `pool/` on the build machine, not in the
  repository.

`releases` (kept on the build machine, not in git) lists the release zip
each package is made from (package, upstream version, build, zip); `./package.sh` packages them all, or
`./package.sh Reel Geany` just those. `package-folio.sh` packages Folio
and its three plugins from their lines in `releases`.

The tools are MIT licensed; each package carries its own licence in
RiscPkg/Copyright.
