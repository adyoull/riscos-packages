#!/bin/sh
# Publishes the package site to GitHub Pages:
#   https://adyoull.github.io/riscos-packages/   (PackMan source: .../pkg/index)
#
# 1. Rebuilds site/ from pool/ (tools/riscpkg.py index).
# 2. Creates adyoull/riscos-packages on GitHub if it isn't there, and pushes
#    main (the tools, the specs and the README; never the zips).
# 3. Pushes site/ as a single commit to the gh-pages branch, replacing the
#    last one, so old package zips don't pile up in the repository's history.
# 4. Turns GitHub Pages on for gh-pages the first time.
# Running it again just updates everything. Needs git and gh, logged in.
set -eu
cd "$(dirname "$0")"
REPO=${REPO:-adyoull/riscos-packages}
OWNER=${REPO%/*}
NAME=${REPO#*/}
BASE=${BASE:-https://$OWNER.github.io/$NAME/}
AUTHOR_NAME="Andrew Youll"
AUTHOR_EMAIL="adyoull@users.noreply.github.com"
export GIT_AUTHOR_NAME="$AUTHOR_NAME" GIT_AUTHOR_EMAIL="$AUTHOR_EMAIL"
export GIT_COMMITTER_NAME="$AUTHOR_NAME" GIT_COMMITTER_EMAIL="$AUTHOR_EMAIL"

gh auth status >/dev/null

python3 tools/riscpkg.py index --base "$BASE"

# --- the repository and main ------------------------------------------
if ! gh repo view "$REPO" >/dev/null 2>&1; then
	gh repo create "$REPO" --public \
		--description "PackMan packages of RISC OS ports and applications"
	gh repo edit "$REPO" --add-topic riscos --add-topic packman \
		--add-topic riscpkg --homepage "$BASE" || true
fi
URL=$(gh repo view "$REPO" --json url -q .url).git

if [ ! -d .git ]; then
	git init -q -b main
	git remote add origin "$URL"
fi
git add -A
if ! git diff --cached --quiet || ! git rev-parse -q --verify HEAD >/dev/null; then
	git commit -q -m "Packaging tools and specs, $(date +%Y-%m-%d)"
fi
git push -q -u origin main

# --- gh-pages: one commit with the current site -----------------------
# .pages/ is a local git repository kept between runs. Each run makes a
# new commit with no history and force-pushes it, so GitHub only ever
# holds the current site; because .pages still has the commit GitHub has,
# git only uploads the zips that changed.
if [ ! -d .pages/.git ]; then
	mkdir -p .pages
	git -C .pages init -q -b gh-pages
fi
find .pages -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -R site/. .pages/
(
	cd .pages
	git checkout -q --orphan next
	git add -A
	git commit -q -m "Packages as of $(date -u +%Y-%m-%dT%H:%MZ)"
	git branch -q -M next gh-pages
	git push -q --force "$URL" gh-pages
	# Keep only what GitHub now has: the next push is measured against it.
	git update-ref refs/published HEAD
	git reflog expire --expire=now --all
	git gc -q --prune=now
)

# --- GitHub Pages ------------------------------------------------------
# GitHub usually turns Pages on by itself when a gh-pages branch is first
# pushed, so asking again can fail; that isn't an error here.
if ! gh api "repos/$REPO/pages" >/dev/null 2>&1; then
	if gh api -X POST "repos/$REPO/pages" \
		-f "source[branch]=gh-pages" -f "source[path]=/" >/dev/null 2>&1; then
		echo "GitHub Pages turned on; the first build takes a minute or two."
	else
		echo "(GitHub Pages: GitHub is already setting it up from gh-pages.)"
	fi
fi

echo "Published: $BASE"
echo "PackMan source: ${BASE}pkg/index"
