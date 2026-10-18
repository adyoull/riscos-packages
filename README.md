# riscos-packages

PackMan packages of RISC OS ports and applications by Andrew Youll.

## Using them

In PackMan, choose **Sources…** from the icon bar menu, add

    https://adyoull.github.io/riscos-packages/pkg/index

and choose **Update lists**. The packages then show in PackMan alongside
the others. The list is also on <https://adyoull.github.io/riscos-packages/>.

| Package | What it is |
|---|---|
| Folio | Reader for PDF and ebook files, built on MuPDF |
| FolioSpeech | Reading aloud for Folio (British English voice) |
| FolioOCR | Text recognition for scanned pages in Folio |
| FolioCJK | Chinese, Japanese and Korean font for Folio |

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

`package-folio.sh N` packages Folio's release 0.0.1-testN and its plugins.

The tools are MIT licensed; each package carries its own licence in
RiscPkg/Copyright.
