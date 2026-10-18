#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""riscpkg.py - turn our release zips into PackMan (RiscPkg) packages and
keep a package index for a static web host (GitHub Pages).

  riscpkg.py build SPEC --from RELEASE.zip --upstream X.Y.Z --build N [--pool DIR]
      Repackages RELEASE.zip (made by the app's own release tools, with RISC
      OS filetypes in the zip) as a RiscPkg package in the pool, named
      <Package>_<version>.zip. The version is <upstream>.0.<build>-<revision>;
      the revision is worked out: 1, or one more than an earlier package of
      the same build whose contents differ. Refuses to go backwards.

  riscpkg.py index [--pool DIR] [--site DIR] [--base URL]
      Builds the web site: the newest package of each name is copied to
      site/packages, and site/pkg/index (the PackMan source), site/pointer
      and site/index.html are written.

  riscpkg.py check PACKAGE.zip
      Checks a package zip on its own.

  riscpkg.py vercmp A B
      Prints <, = or > as PackMan would order the two versions.

A SPEC is a RiscPkg control record (the fields that go into RiscPkg/Control,
without Version) plus build fields starting "Build-":

  Build-Map: <path in release zip> -> <path in package zip> (one or more;
             zip paths with '/', e.g. !Folio -> Apps/Document/!Folio)
  Build-Copyright: <file or directory in release zip>     (one or more)
  Build-Notice: text put at the top of RiscPkg/Copyright (continued lines)
  Build-Untyped: ffd                                      (optional)
      gives files the release zip left without a RISC OS filetype that
      type (UnixLib ports read their data files whatever their type);
      without it such a file stops the build

Only what the maps cover goes into the package; anything else in the
release zip (a loose ReadMe for people unzipping by hand, say) is left out
and listed.
"""

import argparse
import hashlib
import io
import os
import re
import shutil
import sys
import time
import zipfile

SECTIONS = """Administration Archive Audio Chat Communication Database Demo
Desktop Development Device Disc Document File Education Emulation Font Games
Graphics Library Mail Mathematics Miscellaneous Network Presentation Printing
Spreadsheet System Text Video Web""".split()
PRIORITIES = "Required Important Standard Optional Extra".split()
LOGICAL_ROOTS = """Apps Manuals Resources System ToBeLoaded ToBeTasks Boot
Bootloader Diversions Documents Printing Utilities !Boot !System""".split()
REQUIRED = ["Package", "Section", "Priority", "Licence", "Maintainer",
            "Standards-Version", "Description"]
ORDER = ["Package", "Version", "Section", "Priority", "Licence", "Maintainer",
         "Standards-Version", "Environment", "OSDepends", "Depends",
         "Recommends", "Suggests", "Conflicts", "Components", "Homepage",
         "Description"]
INDEX_EXTRA = ["Size", "MD5Sum", "URL"]
MAX_FILE = 100 * 1000 * 1000        # GitHub's limit for one file
SITE_WARN = 900 * 1000 * 1000       # Pages sites should stay under 1 GB


class Fail(Exception):
    pass


# ---------------------------------------------------------------- versions
# The same ordering as LibPkg's version.cc (Debian's): epoch, then the
# upstream version, then the package version; within each, runs of
# non-digits compare by character (~ first, then the end, then letters,
# then the rest by code) and runs of digits compare as numbers.

def split_version(v):
    epoch = 0
    if ":" in v and v.split(":", 1)[0].isdigit():
        e, v = v.split(":", 1)
        epoch = int(e)
    if "-" in v:
        up, pk = v.rsplit("-", 1)
    else:
        up, pk = v, ""
    return epoch, up, pk


def _order(c):
    if c == "~":
        return -1
    if c == "":
        return 0
    if c.isalpha():
        return ord(c)
    return ord(c) + 256


def _cmp_str(a, b):
    i = j = 0
    while i < len(a) or j < len(b):
        # non-digit part
        na = ""
        while i < len(a) and not a[i].isdigit():
            na += a[i]
            i += 1
        nb = ""
        while j < len(b) and not b[j].isdigit():
            nb += b[j]
            j += 1
        for k in range(max(len(na), len(nb))):
            ca = na[k] if k < len(na) else ""
            cb = nb[k] if k < len(nb) else ""
            if ca != cb:
                return -1 if _order(ca) < _order(cb) else 1
        # digit part
        da = ""
        while i < len(a) and a[i].isdigit():
            da += a[i]
            i += 1
        db = ""
        while j < len(b) and b[j].isdigit():
            db += b[j]
            j += 1
        x, y = int(da or "0"), int(db or "0")
        if x != y:
            return -1 if x < y else 1
    return 0


def vercmp(a, b):
    ea, ua, pa = split_version(a)
    eb, ub, pb = split_version(b)
    if ea != eb:
        return -1 if ea < eb else 1
    return _cmp_str(ua, ub) or _cmp_str(pa, pb)


VERSION_RE = re.compile(r"^(\d+:)?[0-9][A-Za-z0-9+.~:-]*(-[A-Za-z0-9+.~]+)?$")


def our_version(upstream, build, revision):
    """<upstream>.0.<build>-<revision>, the scheme in packman-START-HERE."""
    if not re.match(r"^[0-9][A-Za-z0-9+.~]*$", upstream):
        raise Fail("upstream version %r: digits, letters and . + ~ only, "
                   "starting with a digit (no '-')" % upstream)
    if not (str(build).isdigit() and int(build) > 0):
        raise Fail("build number %r: a whole number from 1" % build)
    return "%s.0.%d-%d" % (upstream, int(build), int(revision))


# ---------------------------------------------------------- control records

def parse_control(text, where="control"):
    """A list of records, each a list of (field, value) in file order.
    Continuation lines are kept as written (leading space included)."""
    records, cur, last = [], [], None
    for n, line in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        if line.startswith("#"):
            continue
        if not line.strip():
            if cur:
                records.append(cur)
            cur, last = [], None
            continue
        if line[0] in " \t":
            if last is None:
                raise Fail("%s line %d: continuation with no field" % (where, n))
            k, v = cur[-1]
            cur[-1] = (k, v + "\n" + line)
            continue
        if ": " not in line and not line.rstrip().endswith(":"):
            raise Fail("%s line %d: expected 'Field: value'" % (where, n))
        k, v = line.split(":", 1)
        cur.append((k.strip(), v[1:] if v.startswith(" ") else v))
        last = k
    if cur:
        records.append(cur)
    return records


def get(rec, name, default=None):
    for k, v in rec:
        if k.lower() == name.lower():
            return v
    return default


def get_all(rec, name):
    return [v for k, v in rec if k.lower() == name.lower()]


def format_record(fields):
    """fields: dict-like list of (k, v); written in ORDER, then the rest."""
    d = {}
    for k, v in fields:
        d[k] = v
    keys = [k for k in ORDER if k in d] + \
           [k for k in d if k not in ORDER and k not in INDEX_EXTRA] + \
           [k for k in INDEX_EXTRA if k in d]
    return "".join("%s: %s\n" % (k, d[k]) for k in keys)


# ------------------------------------------------------- RISC OS zip fields

def arc0_type(info):
    """Filetype from the zip's RISC OS extra field (tag 0x4341 'ARC0'), or
    None if there is none, or 'untyped' for load/exec files."""
    e = info.extra
    while len(e) >= 4:
        tag = int.from_bytes(e[0:2], "little")
        size = int.from_bytes(e[2:4], "little")
        body = e[4:4 + size]
        if tag == 0x4341 and body[:4] == b"ARC0" and len(body) >= 12:
            load = int.from_bytes(body[4:8], "little")
            if (load >> 20) == 0xFFF:
                return (load >> 8) & 0xFFF
            return "untyped"
        e = e[4 + size:]
    return None


def arc0_extra(filetype, when, attr=0x33):
    """A RISC OS extra field for a typed, stamped file."""
    t = int((when - (-2208988800)) * 100)      # centiseconds since 1900
    load = 0xFFF00000 | (filetype << 8) | ((t >> 32) & 0xFF)
    exe = t & 0xFFFFFFFF
    body = b"ARC0" + load.to_bytes(4, "little") + exe.to_bytes(4, "little") + \
        attr.to_bytes(4, "little") + bytes(4)
    return (0x4341).to_bytes(2, "little") + len(body).to_bytes(2, "little") + body


# Filetypes for "Build-Untyped: auto", by the name's extension. Only types
# RISC OS's MimeMap gives the same extension, so a UnixLib program that
# uses ",xyz" filetype suffixes still sees the plain name; anything else
# gets the default, normally Text, which UnixLib never adds a suffix for.
EXT_TYPES = {}
for _t, _exts in ((0xFFF, "txt md xml cfg conf ini def lst json html htm css c h cc "
                          "cpp cxx hpp hh s S asm sh mk mak py pl lua csv srt ass "
                          "log diff patch po glsl vert frag ac in am m4 cmake rst "
                          "tex yml yaml toml"),
                  (0xB60, "png"), (0xC85, "jpg jpeg"), (0x695, "gif"),
                  (0xFD4, "mid midi"), (0xFB1, "wav")):
    for _e in _exts.split():
        EXT_TYPES[_e.lower()] = _t
TEXT_NAMES = {"makefile", "readme", "copying", "licence", "license", "authors",
              "changelog", "news", "install", "todo", "version"}


def type_for(name, untyped):
    kind, default = untyped
    if kind == "fixed":
        return default
    leaf = name.rsplit("/", 1)[-1]
    if "." in leaf:
        return EXT_TYPES.get(leaf.rsplit(".", 1)[1].lower(), default)
    if leaf.lower() in TEXT_NAMES or leaf.lower().startswith(("readme", "copying", "licen")):
        return 0xFFF
    return default


# --------------------------------------------------------------- the spec

def read_spec(path):
    with open(path, encoding="utf-8") as f:
        recs = parse_control(f.read(), path)
    if len(recs) != 1:
        raise Fail("%s: one record expected, found %d" % (path, len(recs)))
    rec = recs[0]
    control = [(k, v) for k, v in rec if not k.lower().startswith("build-")]
    if get(control, "Version"):
        raise Fail("%s: leave Version out; it comes from --upstream/--build" % path)
    maps = []
    for m in get_all(rec, "Build-Map"):
        if "->" not in m:
            raise Fail("%s: Build-Map wants 'release/path -> Apps/Section/path'" % path)
        src, dst = (s.strip() for s in m.split("->", 1))
        maps.append((src.strip("/"), dst.strip("/")))
    if not maps:
        raise Fail("%s: no Build-Map" % path)
    copyright_files = [c.strip() for c in get_all(rec, "Build-Copyright")]
    untyped = get(rec, "Build-Untyped")
    if untyped is not None:
        words = untyped.split()
        try:
            if words[0] == "auto":
                untyped = ("auto", int(words[1], 16) if len(words) > 1 else 0xFFF)
            else:
                untyped = ("fixed", int(words[0], 16))
        except (ValueError, IndexError):
            raise Fail("%s: Build-Untyped wants a filetype in hex (e.g. ffd), "
                       "or 'auto' and an optional default type" % path)
    notice = get(rec, "Build-Notice", "")
    notice = "\n".join(l[1:] if l.startswith(" ") else l
                       for l in notice.split("\n"))
    notice = "\n".join("" if l == "." else l for l in notice.split("\n"))
    return control, maps, copyright_files, notice.strip("\n"), untyped


# ------------------------------------------------------------ checks

def check_control(rec, where):
    errs = []
    for k in REQUIRED + ["Version"]:
        if not get(rec, k):
            errs.append("%s: no %s field" % (where, k))
    name = get(rec, "Package", "")
    if name and not re.match(r"^[A-Za-z0-9][A-Za-z0-9+.-]*$", name):
        errs.append("%s: package name %r has characters PackMan won't take" % (where, name))
    v = get(rec, "Version", "")
    if v and not VERSION_RE.match(v):
        errs.append("%s: version %r doesn't follow the policy's syntax" % (where, v))
    s = get(rec, "Section")
    if s and s not in SECTIONS:
        errs.append("%s: section %r isn't one of the policy's sections" % (where, s))
    p = get(rec, "Priority")
    if p and p not in PRIORITIES:
        errs.append("%s: priority %r isn't one of %s" % (where, p, ", ".join(PRIORITIES)))
    lic = get(rec, "Licence")
    if lic and lic not in ("Free", "Non-free"):
        errs.append("%s: Licence must be Free or Non-free" % where)
    for dep_field in ("Depends", "Recommends", "Suggests", "Conflicts"):
        d = get(rec, dep_field)
        if d:
            for item in d.split(","):
                if not re.match(r"^\s*[A-Za-z0-9][A-Za-z0-9+.-]*\s*"
                                r"(\(\s*(<<|<=|=|>=|>>)\s*[^)\s]+\s*\))?\s*$", item):
                    errs.append("%s: %s entry %r isn't 'Name' or 'Name (>= 1.0)'"
                                % (where, dep_field, item.strip()))
    return errs


def components(rec):
    c = get(rec, "Components", "")
    out = []
    for m in re.finditer(r"\s*([^,(]+?)\s*\(([^)]*)\)\s*(,|$)", c):
        out.append((m.group(1), m.group(2).split()))
    if c and not out:
        out.append((c, []))
    return out


def check_zip(path):
    """Checks a package zip; returns (control record, list of errors,
    list of warnings)."""
    errs, warns = [], []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if "RiscPkg/Control" not in names:
            return None, ["%s: no RiscPkg/Control" % path], []
        rec = parse_control(z.read("RiscPkg/Control").decode("latin-1"),
                            path + ":RiscPkg/Control")[0]
        errs += check_control(rec, path)
        if "RiscPkg/Copyright" not in names:
            errs.append("%s: no RiscPkg/Copyright" % path)
        for info in z.infolist():
            n = info.filename
            top = n.split("/", 1)[0]
            if top != "RiscPkg" and top not in LOGICAL_ROOTS:
                errs.append("%s: %s isn't under a logical path the policy knows"
                            % (path, n))
            if info.is_dir():
                continue
            if arc0_type(info) is None:
                errs.append("%s: %s has no RISC OS filetype in the zip" % (path, n))
            if "," in n.rsplit("/", 1)[-1] and re.search(r",[0-9a-f]{3}$", n):
                warns.append("%s: %s still has a ,xxx suffix" % (path, n))
        dirs = {n.rstrip("/") for n in names if n.endswith("/")} | \
               {"/".join(n.split("/")[:i]) for n in names
                for i in range(1, n.count("/") + 1)}
        for comp, opts in components(rec):
            if comp.replace(".", "/") not in dirs and comp.replace(".", "/") not in names:
                errs.append("%s: component %s isn't in the zip" % (path, comp))
            for o in opts:
                if o not in ("Movable", "LookAt", "Run", "AddToApps"):
                    errs.append("%s: component option %r unknown" % (path, o))
    return rec, errs, warns


# --------------------------------------------------------------- build

def payload_key(zf):
    """What the package contains, for 'same build, same contents?'."""
    h = hashlib.sha256()
    for info in sorted(zf.infolist(), key=lambda i: i.filename):
        if info.filename == "RiscPkg/Control":
            text = zf.read(info).decode("latin-1")
            text = re.sub(r"(?m)^Version: .*\n", "", text)
            h.update(b"C" + text.encode("latin-1"))
            continue
        h.update(info.filename.encode() + b"\0")
        h.update(str(arc0_type(info)).encode() + b"\0")
        if not info.is_dir():
            h.update(zf.read(info))
    return h.hexdigest()


def pool_packages(pool):
    """{name: [(version, path)]} from the pool's zips."""
    found = {}
    if not os.path.isdir(pool):
        return found
    for f in sorted(os.listdir(pool)):
        if not f.endswith(".zip"):
            continue
        p = os.path.join(pool, f)
        try:
            with zipfile.ZipFile(p) as z:
                rec = parse_control(z.read("RiscPkg/Control").decode("latin-1"))[0]
        except (KeyError, zipfile.BadZipFile, Fail):
            continue
        found.setdefault(get(rec, "Package"), []).append((get(rec, "Version"), p))
    for k in found:
        found[k].sort(key=lambda vp: _Key(vp[0]))
    return found


class _Key:
    def __init__(self, v):
        self.v = v

    def __lt__(self, o):
        return vercmp(self.v, o.v) < 0


def build(args):
    control, maps, copyright_files, notice, untyped = read_spec(args.spec)
    typed_here = 0
    name = get(control, "Package")
    with zipfile.ZipFile(args.source) as src:
        infos = src.infolist()
        newest = max((i.date_time for i in infos), default=(1980, 1, 1, 0, 0, 0))
        stamp = time.mktime(newest + (0, 0, -1))

        # Map the release zip's paths to the package's.
        out_entries, dropped = [], []
        for info in infos:
            n = info.filename
            dest = None
            for s, d in maps:
                if n.rstrip("/") == s or n.startswith(s + "/"):
                    dest = d + n[len(s):]
                    break
            if dest is None:
                if not info.is_dir():
                    dropped.append(n)
                continue
            out_entries.append((info, dest))
        if not out_entries:
            raise Fail("nothing in %s matches the Build-Map" % args.source)

        # RiscPkg/Copyright: the notice, then each licence file.
        parts = [notice] if notice else []
        names = src.namelist()
        expanded = []
        for c in copyright_files:
            if c in names:
                expanded.append(c)
                continue
            under = sorted(n for n in names
                           if n.startswith(c.rstrip("/") + "/") and not n.endswith("/"))
            if not under:
                raise Fail("Build-Copyright %s isn't in %s" % (c, args.source))
            expanded += under
        for c in expanded:
            parts.append(("-" * 72) + "\n" + c.rsplit("/", 1)[-1] + "\n" +
                         ("-" * 72) + "\n" +
                         src.read(c).decode("latin-1").rstrip("\n"))
        copyright_text = "\n\n".join(parts) + "\n"

        # The version: same build again keeps its revision if nothing
        # changed, else takes the next one; never older than the pool's.
        existing = pool_packages(args.pool).get(name, [])
        prefix = our_version(args.upstream, args.build, 1).rsplit("-", 1)[0]
        same = [(v, p) for v, p in existing if v.rsplit("-", 1)[0] == prefix]
        revision = int(args.revision) if args.revision else None

        def make(rev):
            version = our_version(args.upstream, args.build, rev)
            fields = [("Package", name), ("Version", version)] + \
                [(k, v) for k, v in control if k != "Package"]
            ctext = format_record(fields)
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
                for fname, text in (("RiscPkg/Control", ctext),
                                    ("RiscPkg/Copyright", copyright_text)):
                    zi = zipfile.ZipInfo(fname, newest)
                    zi.create_system = 3
                    zi.external_attr = 0o100644 << 16
                    zi.extra = arc0_extra(0xFFF, stamp)
                    zi.compress_type = zipfile.ZIP_DEFLATED
                    z.writestr(zi, text.encode("latin-1"))
                for info, dest in out_entries:
                    zi = zipfile.ZipInfo(dest, info.date_time)
                    zi.create_system = info.create_system
                    zi.external_attr = info.external_attr
                    zi.extra = info.extra
                    if not info.is_dir() and arc0_type(info) is None:
                        if untyped is None:
                            raise Fail("%s has no RISC OS filetype; give the spec a "
                                       "Build-Untyped: <type> line to set one"
                                       % info.filename)
                        zi.extra = info.extra + arc0_extra(
                            type_for(info.filename, untyped),
                            time.mktime(info.date_time + (0, 0, -1)))
                    if info.is_dir():
                        zi.compress_type = zipfile.ZIP_STORED
                        z.writestr(zi, b"")
                    else:
                        zi.compress_type = zipfile.ZIP_DEFLATED
                        z.writestr(zi, src.read(info))
            return version, buf.getvalue()

        version, data = make(revision or 1)
        if revision is None and same:
            key = payload_key(zipfile.ZipFile(io.BytesIO(data)))
            for v, p in same:
                with zipfile.ZipFile(p) as z:
                    if payload_key(z) == key:
                        print("%s %s: already in the pool with the same contents (%s)"
                              % (name, v, p))
                        return p
            top = max(int(v.rsplit("-", 1)[1]) for v, p in same
                      if v.rsplit("-", 1)[1].isdigit())
            version, data = make(top + 1)
            print("%s: build %s was packaged before with other contents; "
                  "this is revision %d" % (name, args.build, top + 1))
        if existing and vercmp(version, existing[-1][0]) <= 0 and not \
                any(v == version for v, p in existing):
            raise Fail("%s %s isn't newer than %s, already in the pool"
                       % (name, version, existing[-1][0]))
        if any(v == version for v, p in existing):
            raise Fail("%s %s is already in the pool with other contents; "
                       "leave --revision out to get the next one" % (name, version))

    os.makedirs(args.pool, exist_ok=True)
    out = os.path.join(args.pool, "%s_%s.zip" % (name, version))
    tmp = out + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    rec, errs, warns = check_zip(tmp)
    for w in warns:
        print("warning:", w)
    if errs:
        os.remove(tmp)
        raise Fail("the package failed its checks:\n  " + "\n  ".join(errs))
    os.replace(tmp, out)
    for d in dropped:
        print("left out (not in any Build-Map): %s" % d)
    print("made %s (%d bytes)" % (out, len(data)))
    return out


# --------------------------------------------------------------- the site

HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RISC OS packages</title>
<style>
:root {{ --bg:#fbfaf7; --fg:#1d1d1b; --mut:#6b6a66; --line:#e3e0d8; --acc:#1a5fc8; }}
@media (prefers-color-scheme: dark) {{
 :root {{ --bg:#18181a; --fg:#ebe9e4; --mut:#a3a19b; --line:#33322f; --acc:#80b4ff; }} }}
body {{ background:var(--bg); color:var(--fg); font:16px/1.5 system-ui,sans-serif;
  max-width:52rem; margin:0 auto; padding:2rem 16px; }}
h1 {{ font-size:1.6rem; margin:0 0 .25rem }} p.sub {{ color:var(--mut); margin:0 0 2rem }}
code {{ font:0.9em ui-monospace,monospace; background:var(--line); padding:.1em .35em;
  border-radius:4px; overflow-wrap:anywhere }}
table {{ width:100%; border-collapse:collapse; margin-top:1rem }}
th,td {{ text-align:left; padding:.5rem .4rem; border-bottom:1px solid var(--line);
  vertical-align:top }}
th {{ color:var(--mut); font-weight:500; font-size:.85rem }}
td.v {{ font-variant-numeric:tabular-nums; white-space:nowrap }}
a {{ color:var(--acc) }}
</style></head><body>
<h1>RISC OS packages</h1>
<p class="sub">Ports and applications by Andrew Youll, for PackMan.</p>
<h2>Adding this source to PackMan</h2>
<p>In PackMan, choose <b>Sources&hellip;</b> from the icon bar menu, add</p>
<p><code>{index_url}</code></p>
<p>then choose <b>Update lists</b>. The packages below then show in PackMan
with the rest.</p>
<h2>Packages</h2>
<table><tr><th>Package</th><th>Version</th><th>Description</th><th>Size</th></tr>
{rows}
</table>
</body></html>
"""


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def index(args):
    pool = pool_packages(args.pool)
    if not pool:
        raise Fail("no packages in %s" % args.pool)
    base = args.base.rstrip("/") + "/"
    site = args.site
    pkgdir = os.path.join(site, "packages")
    os.makedirs(pkgdir, exist_ok=True)
    os.makedirs(os.path.join(site, "pkg"), exist_ok=True)
    keep, records, rows, pointer = set(), [], [], []
    total = 0
    owner = {}
    for name in sorted(pool, key=str.lower):
        version, path = pool[name][-1]
        rec, errs, warns = check_zip(path)
        if errs:
            raise Fail("\n".join(errs))
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if n.endswith("/") or n.startswith("RiscPkg/"):
                    continue
                if n in owner:
                    raise Fail("%s is in both %s and %s; PackMan would refuse "
                               "to install the second" % (n, owner[n], name))
                owner[n] = name
        leaf = os.path.basename(path)
        keep.add(leaf)
        dst = os.path.join(pkgdir, leaf)
        if not (os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(path)
                and _md5(dst) == _md5(path)):
            shutil.copyfile(path, dst)
        size = os.path.getsize(path)
        if size > MAX_FILE:
            raise Fail("%s is %.1f MB; GitHub Pages won't serve a file over "
                       "100 MB" % (leaf, size / 1e6))
        total += size
        fields = list(rec) + [("Size", str(size)), ("MD5Sum", _md5(path)),
                              ("URL", base + "packages/" + leaf)]
        records.append(format_record(fields))
        pointer.append(base + "packages/" + leaf)
        desc = get(rec, "Description", "").split("\n", 1)[0]
        rows.append("<tr><td>%s</td><td class=v>%s</td><td>%s</td><td class=v>%s</td></tr>"
                    % (esc(name), esc(version), esc(desc), "%.1f MB" % (size / 1e6)))
        print("index: %s %s" % (name, version))
    for f in os.listdir(pkgdir):
        if f not in keep:
            os.remove(os.path.join(pkgdir, f))
            print("index: dropped old %s from the site" % f)
    _write(os.path.join(site, "pkg", "index"), "\n".join(records))
    _write(os.path.join(site, "pointer"), "\n".join(pointer) + "\n")
    _write(os.path.join(site, ".nojekyll"), "")
    _write(os.path.join(site, "index.html"),
           HTML.format(index_url=esc(base + "pkg/index"), rows="\n".join(rows)))
    print("index: %d package(s), %.0f MB; PackMan source %spkg/index"
          % (len(records), total / 1e6, base))
    if total > SITE_WARN:
        print("warning: the site is %.0f MB; GitHub Pages sites should stay "
              "under 1 GB" % (total / 1e6))


def _md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _write(p, text):
    with open(p, "w", encoding="latin-1", newline="\n") as f:
        f.write(text)


# ---------------------------------------------------------------- main

def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("spec")
    b.add_argument("--from", dest="source", required=True)
    b.add_argument("--upstream", required=True)
    b.add_argument("--build", required=True)
    b.add_argument("--revision")
    b.add_argument("--pool", default=os.path.join(here, "pool"))
    i = sub.add_parser("index")
    i.add_argument("--pool", default=os.path.join(here, "pool"))
    i.add_argument("--site", default=os.path.join(here, "site"))
    i.add_argument("--base", default="https://adyoull.github.io/riscos-packages/")
    c = sub.add_parser("check")
    c.add_argument("zip", nargs="+")
    v = sub.add_parser("vercmp")
    v.add_argument("a")
    v.add_argument("b")
    args = ap.parse_args()
    try:
        if args.cmd == "build":
            build(args)
        elif args.cmd == "index":
            index(args)
        elif args.cmd == "check":
            bad = 0
            for z in args.zip:
                rec, errs, warns = check_zip(z)
                for m in warns:
                    print("warning:", m)
                for m in errs:
                    print("error:", m)
                bad += bool(errs)
                if not errs:
                    print("%s: %s %s, fine" % (z, get(rec, "Package"), get(rec, "Version")))
            return 1 if bad else 0
        else:
            print({-1: "<", 0: "=", 1: ">"}[vercmp(args.a, args.b)])
    except Fail as e:
        print("riscpkg: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
