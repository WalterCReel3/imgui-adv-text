.PHONY: help bootstrap venv-info test lint format format-file typecheck check svg run \
        shot shot-all shot-headless clean typeset-lib typeset-pair-is-stale dist

# ---------------------------------------------------------------------------
# Which interpreter runs everything
#
# This project's own virtualenv, ./.venv, and nothing else. `make bootstrap`
# builds it; until it exists every target that needs an interpreter stops with
# one line pointing there.
#
# This file used to fall back to a *borrowed* interpreter from a sibling
# project (pptmstr's .venv) when ./.venv was absent, because the sandbox this
# project was first built in could not run `pip install`. That fallback is
# removed, and deliberately: the goal is for pptmstr to depend on advtext, and
# a project cannot be depended on by the one its build reaches back into. It
# also hid a real difference -- the borrowed venv had no numpy and ran tool
# versions far ahead of pyproject.toml's floors -- behind a build that looked
# the same either way. pyproject.toml is the dependency declaration; ./.venv
# is where it is installed.
#
# `PY` can still be overridden on the command line (tests/test_shot_all.py
# reads the shot-all recipe without opening a window by pointing PY at a stub
# that answers --list and echoes everything else), and an overridden PY is the
# caller's business: the ./.venv guard below applies only while PY is the
# default.
VENV      ?= .venv
VENV_PY   := $(VENV)/bin/python
PY        := $(VENV_PY)
BIN       := $(dir $(PY))

# The guard. A target lists $(NEED_VENV) as an order-only prerequisite; while
# PY is the default that is the interpreter's own path, and the rule below is
# how make "builds" it when the file is absent -- by refusing. When the file
# exists the rule has nothing to do and its recipe never runs. Order-only (`|`)
# so the interpreter's mtime never makes anything look out of date.
NEED_VENV := $(if $(filter $(VENV_PY),$(PY)),$(VENV_PY))

$(VENV_PY):
	@echo "No $(VENV_PY). Run 'make bootstrap' to build ./.venv (needs network)." >&2; exit 2

# `ruff check` fails on a path that is absent, so `scripts` and `examples` join
# the set by wildcard: each was added before the first file in it landed, and a
# checkout or an sdist that lacks one still lints.
#
# `examples` is here because an example is the code a host copies. One that
# does not pass the project's own lint is a worse advertisement than none.
SRC := advtext tests $(wildcard scripts) $(wildcard examples)

.DEFAULT_GOAL := help

# ---------------------------------------------------------------------------
# imtypeset: what draws (branch experimental/imtypeset-adoption)
#
# Since 2026-10-11 the imtypeset library is the ONLY thing that sets and draws
# text in the demo and the examples: advtext's own views and its ImGui draw
# backend are deleted. advtext/typesetter.py loads the library when two
# environment variables say where it is. When they do not, every page draws
# one line saying so and nothing else, and the suite's with-library tests
# skip: plain `make check` is green without the library and proves less.
# (Until that date this paragraph read "and exactly as before when they do
# not": the old views were the fallback.) Nothing here sets the variables
# unless the caller asks:
#
#   make typeset-lib              build the library for ./.venv's wheel, from
#                                 IMTYPESET_ROOT's working tree
#   make typeset-lib IMTYPESET_COMMIT=<rev>
#                                 the same from that commit of IMTYPESET_ROOT,
#                                 whatever its working tree holds (see below)
#   make typeset-lib IMTYPESET_REF=<tag or full commit hash>
#                                 the same from IMTYPESET_REPO (GitHub) at that
#                                 ref, with no sibling checkout of imtypeset
#                                 (see below; needs network)
#   make test TYPESET=1           the suite with it (the tests that need it run
#                                 instead of skipping); likewise check, run,
#                                 shot, shot-all
#   IMTYPESET_LIBRARY=/some/lib.so make test     the same with another library
#
# With neither, TYPESET_ENV is empty and every recipe below is character for
# character what it was. With either, a recipe gains two assignments in front
# of its command and nothing else -- the command's own arguments do not change,
# which is what lets tests/test_shot_all.py read the shot-all recipe either way.
#
# IMTYPESET_PYTHON is where the ctypes package is (advtext/typesetter.py puts it
# on sys.path itself). It is not passed as PYTHONPATH because a child process
# that sets its own PYTHONPATH -- tests/conftest.py's `window` does -- would
# keep the library and lose the package.
#
# IMTYPESET_ROOT is a sibling checkout and that is deliberate here in a way the
# borrowed interpreter above was not: it is read only by `make typeset-lib`,
# and advtext builds, lints and passes its plain suite without it. What it
# does not do without the built library is draw (above).
# `make clean` removes build/, and the library with it.
IMTYPESET_ROOT    ?= ../imtypeset
IMTYPESET_BUNDLE  ?= $(CURDIR)/build/imtypeset-bundle
# Names beside the bundle are made by appending to this (.building and
# .previous), so it is made absolute and loses a trailing slash here, wherever
# it was given: `IMTYPESET_BUNDLE=some/dir/` used to stage INSIDE the bundle
# and fail at the last rename, after the whole build. `override` because a
# variable from the command line otherwise outranks an assignment in this file.
override IMTYPESET_BUNDLE := $(abspath $(IMTYPESET_BUNDLE))
# The library's FILE NAME is the build script's to say, not this file's: it
# differs by platform (imtypeset's H16: .so on Linux, .dylib on macOS). From
# imtypeset 03b5cd4 on the script writes it to <out>/LIBRARY, and what
# `make typeset-lib` installs keeps that file (see there); the name is read
# from it. Only the NAME is taken: the directory is IMTYPESET_BUNDLE, so a
# bundle that was moved or copied still names its own library.
#
# Where there is no LIBRARY file -- a pair built from a commit before 03b5cd4
# (the script wrote none), or nothing built yet -- the name is the one that
# script gives on this system. That is a guess only in the second case, and
# only `make typeset-lib test TYPESET=1` in one invocation depends on it.
typeset_named     := $(if $(wildcard $(IMTYPESET_BUNDLE)/LIBRARY),$(notdir $(shell sed -n 1p "$(IMTYPESET_BUNDLE)/LIBRARY" 2>/dev/null)))
IMTYPESET_BUILT   := $(IMTYPESET_BUNDLE)/$(or $(typeset_named),libimtypeset_bundle.$(if $(filter Darwin,$(shell uname -s)),dylib,so))
TYPESET           ?=

ifneq ($(filter-out 0,$(strip $(TYPESET))),)
  IMTYPESET_LIBRARY ?= $(IMTYPESET_BUILT)
endif
ifneq ($(strip $(IMTYPESET_LIBRARY)),)
  # Asked for and not there is an error, not a suite that quietly skips: the
  # same shape as the ./.venv guard above. The rule is how make "builds" the
  # file when it is absent -- by refusing -- and it exists only when asked.
  NEED_TYPESET := $(abspath $(IMTYPESET_LIBRARY))
  # The package that goes with the library is the one `make typeset-lib` copied
  # beside it when it built it (see there), when there is one; the sibling
  # checkout's live package otherwise, as before. A caller's own
  # IMTYPESET_PYTHON, on the command line or in the environment, wins.
  IMTYPESET_SNAPSHOT := $(dir $(NEED_TYPESET))pysnap
  # `make typeset-lib test TYPESET=1` in one invocation: everything here is
  # settled when this file is read, which is before typeset-lib has run. Where
  # there was no snapshot yet, the suite was handed the new library with the
  # sibling checkout's live package (measured, 2026-10-11). The build always
  # leaves a snapshot, so when it is among the goals and the library asked for
  # is the one it builds, the snapshot is the answer without looking.
  typeset_building := $(and $(filter typeset-lib,$(MAKECMDGOALS)),$(filter $(IMTYPESET_BUILT),$(NEED_TYPESET)))
  IMTYPESET_PYTHON ?= $(if $(or $(typeset_building),$(wildcard $(IMTYPESET_SNAPSHOT)/imtypeset/__init__.py)),$(IMTYPESET_SNAPSHOT),$(abspath $(IMTYPESET_ROOT))/python)
  typeset_empty :=
  TYPESET_ENV := IMTYPESET_LIBRARY=$(NEED_TYPESET) IMTYPESET_PYTHON=$(IMTYPESET_PYTHON)$(typeset_empty) $(typeset_empty)

$(NEED_TYPESET):
	@echo "No $@. 'make typeset-lib' builds the library and its package into $(IMTYPESET_BUNDLE) (needs $(IMTYPESET_ROOT))." >&2; exit 2

  # A stale pair, refused. `make typeset-lib` ends by writing the library's
  # checksum into BUILT-FROM. Something else that replaces the library where it
  # lies -- the build script run by hand into the same directory, a copy --
  # leaves the snapshot of the build before beside it, and the snapshot was
  # then preferred without a word. So: when the package about to be used IS
  # that snapshot, and BUILT-FROM records a checksum, and the library has
  # another, the targets that would use the pair stop.
  #
  # Every doubt goes the other way, so that a good pair is never refused: no
  # BUILT-FROM, or one from before the line existed, no `cksum`, no library
  # (the rule above speaks for that), a caller's own IMTYPESET_PYTHON, or a
  # library with no snapshot beside it -- none of these is called stale.
  # `cksum` is POSIX's CRC and byte count: a check against an accident, which
  # is all this is, and it reads the library in a few milliseconds.
  typeset_stale :=
  ifeq ($(typeset_building),)
  ifeq ($(IMTYPESET_PYTHON),$(IMTYPESET_SNAPSHOT))
    typeset_stale := $(shell \
      want=$$(sed -n 's/^library cksum: //p' "$(dir $(NEED_TYPESET))BUILT-FROM" 2>/dev/null | head -n 1); \
      have=$$(cksum < "$(NEED_TYPESET)" 2>/dev/null); \
      [ -z "$$want" ] || [ -z "$$have" ] || [ "$$want" = "$$have" ] || echo "$$have, not $$want")
  endif
  endif
  ifneq ($(strip $(typeset_stale)),)
    NEED_PAIR := typeset-pair-is-stale

typeset-pair-is-stale:
	@echo "$(NEED_TYPESET) is not the library its BUILT-FROM describes (cksum $(typeset_stale)), so $(IMTYPESET_SNAPSHOT) is the package of another build. 'make typeset-lib' builds a pair that matches; IMTYPESET_PYTHON=... names another package yourself." >&2; exit 2
  endif
endif

# One library per interpreter: it is linked against that interpreter's
# imgui-bundle wheel and refuses any other at import. The script reads
# IMTYPESET_ROOT's WORKING TREE and writes only under IMTYPESET_BUNDLE (and,
# from imtypeset 03b5cd4 on, the headers it fetched under
# IMTYPESET_HEADER_CACHE); it ends
# by running the import gate and fails if the gate refuses. Its first argument
# is a Dear ImGui Bundle checkout and its second the interpreter.
#
# From GitHub at a named ref rather than from a checkout beside this one:
#
#   make typeset-lib IMTYPESET_REF=v0.1.0
#   make typeset-lib IMTYPESET_REF=c9f8902a67adf00a18426876d5983617b7d1408c
#
# Both projects are public (HANDOFF-imtypeset.md, rule 4: "builds refer to
# GitHub, by tag"). IMTYPESET_REF is a tag, a branch, or a FULL 40-character
# commit hash -- the remote resolves it, and no remote resolves an abbreviated
# hash. That one commit is fetched (`git fetch --depth 1`) from IMTYPESET_REPO
# into IMTYPESET_CACHE, a bare repository under build/ that is this target's
# own, and from there on the build is IMTYPESET_COMMIT's: `git archive` of the
# resolved hash into the staging directory, script, sources and package
# snapshot from that extract. BUILT-FROM names the URL, the ref as it was
# given, and the full hash it resolved to (a tag or a branch can move; the hash
# is what was built). IMTYPESET_ROOT is not read at all.
#
# The fetch is the first thing the recipe does. No network, a ref the remote
# does not have, or a ref that is not a commit stops there, with a line saying
# what to do, before the staging directory or the installed pair is touched.
# GIT_TERMINAL_PROMPT=0 because GitHub answers a repository it does not know
# by asking for a user name, and a build that waits at a prompt is a hang.
#
# IMTYPESET_REPO can be any URL git fetches from; tests/test_makefile_env.py
# uses file:// ones. IMTYPESET_REF and IMTYPESET_COMMIT together are refused:
# they name two sources.
#
# What the build script reads beside imtypeset is NOT fetched here: a Dear
# ImGui Bundle checkout (IMGUI_BUNDLE_CHECKOUT) and, for stand-in headers, a
# Dear ImGui clone (IMTYPESET_IMGUI_CLONE). With a sibling imtypeset both are
# looked for beside IT, as before; with IMTYPESET_REF there is no sibling, and
# both are looked for beside THIS repository (../imgui_bundle, ../imgui).
# A script from before imtypeset 03b5cd4 needs both. From 03b5cd4 on neither
# need exist where the script can fetch (IMTYPESET_HEADERS, below): the
# checkout is then only a way to read the bundle's configuration header
# without network, and the clone is read only for stand-in headers.
IMTYPESET_REPO  ?= https://github.com/WalterCReel3/imtypeset.git
IMTYPESET_REF   ?=
IMTYPESET_CACHE ?= $(CURDIR)/build/imtypeset-cache
typeset_beside  := $(if $(strip $(IMTYPESET_REF)),$(abspath $(CURDIR)/..),$(abspath $(IMTYPESET_ROOT))/..)
ifneq ($(strip $(IMTYPESET_REF)),)
  # Where the fetched commit is kept between the recipe's first step and the
  # one that archives it: a ref of the cache named by what was asked for, so
  # two builds sharing a cache do not read one another's FETCH_HEAD.
  typeset_fetched := refs/typeset-lib/$(shell printf '%s' '$(IMTYPESET_REPO) $(IMTYPESET_REF)' | cksum | tr ' ' '-')
endif
IMGUI_BUNDLE_CHECKOUT ?= $(typeset_beside)/imgui_bundle

# From a commit rather than from whatever the working tree holds:
#
#   make typeset-lib IMTYPESET_COMMIT=12d77ac
#
# A working tree other people are changing is not reproducible, and the
# imtypeset team names the commit to build from in
# $(IMTYPESET_ROOT)/docs/advtext-swap-status.md ("Build from"). The commit is
# resolved once, taken out of IMTYPESET_ROOT's object store with `git archive`
# (which reads there and writes nothing) into the staging directory's src/,
# and the pair is built from that extract: script, sources and package
# snapshot alike. BUILT-FROM then names the repository, the full hash, and no
# uncommitted paths. The extract is installed with the pair, as
# IMTYPESET_BUNDLE/src: the source of exactly the library beside it (about
# 100 MB for imtypeset today), replaced or left alone with it like the rest.
#
# The script looks for its two neighbours (the Dear ImGui Bundle checkout and
# a Dear ImGui clone) beside its own checkout, and the extract has neither, so
# both are named from IMTYPESET_ROOT.
IMTYPESET_COMMIT      ?=
IMTYPESET_IMGUI_CLONE ?= $(typeset_beside)/imgui

# Which Dear ImGui headers the library is compiled against is said HERE, to
# the script, and never left to it (imtypeset's T1). From imtypeset 03b5cd4 on
# the script fetches the wheel's own headers (the fork, by commit id; network,
# once per wheel version) and no longer falls back to upstream's by itself.
#
#   IMTYPESET_HEADERS=            (the default) the script's own choice, which
#                                 is the fetch. No network and nothing cached:
#                                 the build stops there and says so.
#   IMTYPESET_HEADERS=stand-in    upstream Dear ImGui's headers, from
#                                 IMTYPESET_IMGUI_CLONE: what every pair built
#                                 here before 03b5cd4 was, and the only choice
#                                 without network. `typesetter.pairing()`
#                                 says `headers: stand-in:...` of such a pair.
#   IMTYPESET_HEADERS=fork        the fetch, said aloud.
#
# The word is handed over as IMTYPESET_BUNDLE_HEADERS, the script's name for
# it; a script from before 03b5cd4 does not read it and chooses as it always
# did (the fork when a checkout beside it has it, stand-in otherwise).
#
# What is fetched is kept in IMTYPESET_HEADER_CACHE, under this repository's
# build/. The script's own default is build/bundle-headers of the tree it runs
# from: with IMTYPESET_COMMIT or IMTYPESET_REF that is the staging directory,
# gone at the next build, and with neither it is a write into the sibling
# checkout, which this target otherwise never makes.
IMTYPESET_HEADERS      ?=
IMTYPESET_HEADER_CACHE ?= $(CURDIR)/build/imtypeset-headers

# The library and the Python package that calls it are a PAIR. The package is
# ctypes declarations of the library's exports, both come from one working
# tree that other people change, and a package newer than the library fails at
# import on the first function the library lacks (2026-10-10: every
# with-library test, on ImTypeset_GetFontAtlasIndex). So the target leaves
# these in IMTYPESET_BUNDLE, not only the first:
#
#   the library              under the name the build script gave it
#   LIBRARY                  one line, the library's path where it is
#                            installed (from imtypeset 03b5cd4 on; the script
#                            writes it naming the staging directory and this
#                            target rewrites it; IMTYPESET_BUILT above reads
#                            the name from it)
#   <library>.attestation.json
#                            the script's record that its full probe accepted
#                            this library beside this wheel (from 03b5cd4 on).
#                            It is about content, not paths, so it is carried
#                            as it is; without it every import probes the
#                            library in a child interpreter
#   pysnap/imtypeset/        the package as it was when the library was built
#                            (what IMTYPESET_PYTHON defaults to, above). Its
#                            modules and nothing else: from imtypeset v0.3.0
#                            on a package directory that holds a library or
#                            an _attestation.json is an installed
#                            distribution and reads neither variable, so
#                            the library stays BESIDE pysnap and never goes
#                            into it (tests/test_typesetter_pairing.py)
#   BUILT-FROM               the checkout, its HEAD (or IMTYPESET_COMMIT), how
#                            many paths were uncommitted, when, and the
#                            library's checksum (what the stale-pair check
#                            above reads). With IMTYPESET_REF: the URL in
#                            place of the checkout, a `ref:` line, and the
#                            hash the ref resolved to
#
# BUILT-FROM's git lines are about IMTYPESET_ROOT's OWN repository. A directory
# that is not the top of one -- an extract lying inside this repository, say --
# is "not a git checkout", never the repository that happens to enclose it
# (2026-10-11: such a file named advtext's HEAD as imtypeset's).
#
# The package is copied just before the build starts reading sources, which is
# as close to "the same tree" as a copy of a tree in motion gets; the last step
# before anything is put in place imports the COPY against the new library, so
# a pair that does not load is never installed.
#
# All of it is made in IMTYPESET_BUNDLE.building and renamed into place at the
# end, whole. A build that fails at any step leaves IMTYPESET_BUNDLE exactly as
# it was (and .building behind, to look at; the next run removes it).
# IMTYPESET_BUNDLE is therefore this target's own directory: anything else in
# it goes when a build succeeds.
#
# Nothing here writes, removes or expects <library>.gate (imtypeset's T3). A
# pair built from a commit before 03b5cd4 has one: that package's own memory
# of its gate, keyed on the library's path. The one its script writes while
# staging names the staging path and is left where it is; that package finds
# it stale at the first import from the final place and writes its own.
IMTYPESET_STAGE   := $(IMTYPESET_BUNDLE).building
IMTYPESET_EXTRACT := $(IMTYPESET_STAGE)/src
IMTYPESET_SOURCE  := $(if $(strip $(IMTYPESET_COMMIT)$(IMTYPESET_REF)),$(IMTYPESET_EXTRACT),$(IMTYPESET_ROOT))

typeset-lib: | $(NEED_VENV)  ## build the imtypeset library and its package snapshot into build/imtypeset-bundle (needed to draw; IMTYPESET_COMMIT=<rev> builds that commit, IMTYPESET_REF=<tag> fetches it from GitHub)
ifneq ($(strip $(IMTYPESET_REF)),)
ifneq ($(strip $(IMTYPESET_COMMIT)),)
	@echo "IMTYPESET_REF=$(IMTYPESET_REF) and IMTYPESET_COMMIT=$(IMTYPESET_COMMIT) name two sources. Give one: IMTYPESET_REF fetches from $(IMTYPESET_REPO), IMTYPESET_COMMIT reads the checkout at $(IMTYPESET_ROOT)." >&2; exit 2
endif
	@[ -d "$(IMTYPESET_CACHE)" ] || git init --quiet --bare "$(IMTYPESET_CACHE)" || { \
	  echo "IMTYPESET_REF=$(IMTYPESET_REF) needs git and a cache it can write: IMTYPESET_CACHE=$(IMTYPESET_CACHE) could not be made." >&2; exit 2; }
	@GIT_TERMINAL_PROMPT=0 git --git-dir="$(IMTYPESET_CACHE)" fetch --quiet --depth 1 --no-tags "$(IMTYPESET_REPO)" "$(IMTYPESET_REF)" || { \
	  echo "IMTYPESET_REF=$(IMTYPESET_REF) could not be fetched from $(IMTYPESET_REPO): no network, or the repository has no such tag, branch or FULL commit hash (an abbreviated hash is not fetchable). Nothing was built and the installed pair is untouched. With a checkout of imtypeset on this machine, 'make typeset-lib IMTYPESET_COMMIT=<rev>' (IMTYPESET_ROOT=$(IMTYPESET_ROOT)) builds without network; IMTYPESET_REPO=... names another repository." >&2; exit 2; }
	@commit=$$(git --git-dir="$(IMTYPESET_CACHE)" rev-parse --verify --quiet "FETCH_HEAD^{commit}") \
	  && git --git-dir="$(IMTYPESET_CACHE)" update-ref "$(typeset_fetched)" "$$commit" || { \
	  echo "IMTYPESET_REF=$(IMTYPESET_REF) of $(IMTYPESET_REPO) was fetched and is not a commit (or a tag of one)." >&2; exit 2; }
else ifeq ($(strip $(IMTYPESET_COMMIT)),)
	@test -f "$(IMTYPESET_ROOT)/python/host/build_bundle_library.sh" || { \
	  echo "No imtypeset checkout at $(IMTYPESET_ROOT). Set IMTYPESET_ROOT=..." >&2; exit 2; }
else
	@top=$$(git -C "$(IMTYPESET_ROOT)" rev-parse --show-toplevel 2>/dev/null) \
	  && [ "$$top" = "$$(cd "$(IMTYPESET_ROOT)" && pwd -P)" ] || { \
	  echo "IMTYPESET_COMMIT=$(IMTYPESET_COMMIT) needs a git checkout of imtypeset, and $(IMTYPESET_ROOT) is not the top of one. Set IMTYPESET_ROOT=..." >&2; exit 2; }
	@git -C "$(IMTYPESET_ROOT)" rev-parse --verify --quiet --end-of-options "$(IMTYPESET_COMMIT)^{commit}" >/dev/null || { \
	  echo "IMTYPESET_COMMIT=$(IMTYPESET_COMMIT) names no commit of $(IMTYPESET_ROOT)." >&2; exit 2; }
endif
	rm -rf "$(IMTYPESET_STAGE)"
	mkdir -p "$(IMTYPESET_STAGE)/pysnap/imtypeset"
ifneq ($(strip $(IMTYPESET_REF)),)
	@set -e; \
	commit=$$(git --git-dir="$(IMTYPESET_CACHE)" rev-parse --verify --quiet "$(typeset_fetched)^{commit}"); \
	echo "git archive $$commit ($(IMTYPESET_REF) of $(IMTYPESET_REPO)) -> $(IMTYPESET_EXTRACT)"; \
	mkdir "$(IMTYPESET_EXTRACT)"; \
	git --git-dir="$(IMTYPESET_CACHE)" archive --format=tar -o "$(IMTYPESET_EXTRACT).tar" "$$commit"; \
	tar -xf "$(IMTYPESET_EXTRACT).tar" -C "$(IMTYPESET_EXTRACT)"; \
	rm -f "$(IMTYPESET_EXTRACT).tar"; \
	test -f "$(IMTYPESET_EXTRACT)/python/host/build_bundle_library.sh" || { \
	  echo "Commit $$commit ($(IMTYPESET_REF) of $(IMTYPESET_REPO)) has no python/host/build_bundle_library.sh." >&2; exit 2; }; \
	{ echo "imtypeset: $(IMTYPESET_REPO)"; \
	  echo "ref: $(IMTYPESET_REF)"; \
	  echo "commit: $$commit"; \
	  echo "uncommitted paths: 0 (an archive of a commit)"; \
	  echo "date: $$(date -u +%Y-%m-%dT%H:%M:%SZ)"; \
	  echo "by: make typeset-lib IMTYPESET_REF=$(IMTYPESET_REF)"; } > "$(IMTYPESET_STAGE)/BUILT-FROM"
else ifeq ($(strip $(IMTYPESET_COMMIT)),)
	@{ echo "imtypeset: $(abspath $(IMTYPESET_ROOT))"; \
	  if top=$$(git -C "$(IMTYPESET_ROOT)" rev-parse --show-toplevel 2>/dev/null) \
	     && [ "$$top" = "$$(cd "$(IMTYPESET_ROOT)" && pwd -P)" ] \
	     && commit=$$(git -C "$(IMTYPESET_ROOT)" rev-parse HEAD 2>/dev/null); then \
	    echo "commit: $$commit"; \
	    echo "uncommitted paths: $$(git --no-optional-locks -C "$(IMTYPESET_ROOT)" status --short | wc -l | tr -d ' ')"; \
	  else \
	    echo "commit: unknown (not a git checkout)"; \
	    echo "uncommitted paths: unknown"; \
	  fi; \
	  echo "date: $$(date -u +%Y-%m-%dT%H:%M:%SZ)"; \
	  echo "by: make typeset-lib"; } > "$(IMTYPESET_STAGE)/BUILT-FROM"
else
	@set -e; \
	commit=$$(git -C "$(IMTYPESET_ROOT)" rev-parse --verify --quiet --end-of-options "$(IMTYPESET_COMMIT)^{commit}"); \
	echo "git archive $$commit of $(abspath $(IMTYPESET_ROOT)) -> $(IMTYPESET_EXTRACT)"; \
	mkdir "$(IMTYPESET_EXTRACT)"; \
	git -C "$(IMTYPESET_ROOT)" archive --format=tar -o "$(IMTYPESET_EXTRACT).tar" "$$commit"; \
	tar -xf "$(IMTYPESET_EXTRACT).tar" -C "$(IMTYPESET_EXTRACT)"; \
	rm -f "$(IMTYPESET_EXTRACT).tar"; \
	test -f "$(IMTYPESET_EXTRACT)/python/host/build_bundle_library.sh" || { \
	  echo "Commit $$commit of $(IMTYPESET_ROOT) has no python/host/build_bundle_library.sh." >&2; exit 2; }; \
	{ echo "imtypeset: $(abspath $(IMTYPESET_ROOT))"; \
	  echo "commit: $$commit"; \
	  echo "uncommitted paths: 0 (an archive of a commit)"; \
	  echo "date: $$(date -u +%Y-%m-%dT%H:%M:%SZ)"; \
	  echo "by: make typeset-lib IMTYPESET_COMMIT=$(IMTYPESET_COMMIT)"; } > "$(IMTYPESET_STAGE)/BUILT-FROM"
endif
	cp -R "$(IMTYPESET_SOURCE)/python/imtypeset/." "$(IMTYPESET_STAGE)/pysnap/imtypeset/"
	find "$(IMTYPESET_STAGE)/pysnap" -name __pycache__ -type d -prune -exec rm -rf {} +
	$(if $(strip $(IMTYPESET_COMMIT)$(IMTYPESET_REF)),IMTYPESET_IMGUI_CLONE="$(IMTYPESET_IMGUI_CLONE)" )$(if $(strip $(IMTYPESET_HEADERS)),IMTYPESET_BUNDLE_HEADERS=$(strip $(IMTYPESET_HEADERS)) )IMTYPESET_HEADER_CACHE="$(IMTYPESET_HEADER_CACHE)" IMTYPESET_BUNDLE_OUT=$(IMTYPESET_STAGE) sh $(IMTYPESET_SOURCE)/python/host/build_bundle_library.sh \
	  "$(IMGUI_BUNDLE_CHECKOUT)" "$(abspath $(PY))"
	@set -e; \
	named=$$(sed -n 1p "$(IMTYPESET_STAGE)/LIBRARY" 2>/dev/null || true); \
	name=$$(basename "$${named:-libimtypeset_bundle.so}"); \
	staged="$(IMTYPESET_STAGE)/$$name"; \
	test -f "$$staged" || { \
	  echo "The build script left no library at $$staged ($${named:+its LIBRARY file names $$named; }nothing was installed)." >&2; exit 2; }; \
	echo "import $$staged with $(IMTYPESET_STAGE)/pysnap"; \
	IMTYPESET_LIBRARY="$$staged" "$(abspath $(PY))" -P -B -c \
	  'import sys; sys.path.insert(0, sys.argv[1]); import imtypeset' "$(IMTYPESET_STAGE)/pysnap"; \
	if [ -n "$$named" ]; then \
	  echo "$(IMTYPESET_BUNDLE)/$$name" > "$(IMTYPESET_STAGE)/LIBRARY"; \
	  [ -f "$$staged.attestation.json" ] || echo "note: the build left no $$name.attestation.json; every import of this pair probes the library in a child interpreter" >&2; \
	fi; \
	echo "library cksum: $$(cksum < "$$staged")" >> "$(IMTYPESET_STAGE)/BUILT-FROM"
	@rm -rf "$(IMTYPESET_BUNDLE).previous"; \
	if [ -e "$(IMTYPESET_BUNDLE)" ]; then mv "$(IMTYPESET_BUNDLE)" "$(IMTYPESET_BUNDLE).previous" || exit 1; fi; \
	if mv "$(IMTYPESET_STAGE)" "$(IMTYPESET_BUNDLE)"; then \
	  rm -rf "$(IMTYPESET_BUNDLE).previous"; \
	else \
	  [ ! -e "$(IMTYPESET_BUNDLE).previous" ] || mv "$(IMTYPESET_BUNDLE).previous" "$(IMTYPESET_BUNDLE)"; \
	  exit 1; \
	fi
	@cat "$(IMTYPESET_BUNDLE)/BUILT-FROM"
	@echo "installed: $(IMTYPESET_BUNDLE) (the build script's 'use it with' line above names the staging directory)"
	@named=$$(sed -n 1p "$(IMTYPESET_BUNDLE)/LIBRARY" 2>/dev/null || true); \
	echo "use it with: IMTYPESET_LIBRARY=$${named:-$(IMTYPESET_BUNDLE)/libimtypeset_bundle.so} IMTYPESET_PYTHON=$(IMTYPESET_BUNDLE)/pysnap (what 'make ... TYPESET=1' sets)"

# ---------------------------------------------------------------------------
# Looking at the GUI: `make shot`, and `make shot-headless` when there is no
# display
#
# This file has now held three beliefs about running a window here. The first
# was pptmstr's `xvfb-run` recipe under a note saying a windowed target could
# not run and would hang. The second replaced it with `scripts/shot.sh`, an
# Xvfb inside a user namespace, on the grounds that no display was reachable.
# Both were believed long enough to shape task specifications and two
# documents. The third was measured rather than inferred, in the session that
# wrote it:
#
#   DISPLAY=:1 is live and a real window opens on it in about half a second.
#   No Xvfb, no namespace, no software rasteriser.
#
# Two claims that justified the namespace were also false in that session and
# were checked individually rather than assumed to fall with it:
#
#   "AF_UNIX sockets are blocked"   they were not. socket(AF_UNIX) connected to
#                                   /tmp/.X11-unix/X1, which is how DISPLAY=:1
#                                   works at all.
#   "numpy cannot be installed"     it is installed, as a dev dependency, which
#                                   is what makes hello_imgui's own screenshot
#                                   call usable. cv2 is not needed by it.
#
# And a fourth (2026-10-06 and 07), also measured: all three are facts about a
# session and not about the machine. In the sandboxed session that built
# docs/adoption-plan.md, DISPLAY=:1 was set and unreachable -- socket(AF_UNIX)
# raised PermissionError -- and `make shot` died in GLFW. What opened a window
# there was an Xvfb in a user namespace listening on TCP with `-nolisten unix`,
# which is the shell `scripts/mouse_probe.py::xvfb_command` builds; the tests
# that need a window use it when DISPLAY does not answer (tests/conftest.py,
# `window`). `scripts/shot.sh` (`make shot-headless`) is the older form of the
# same idea and was not run in that session. So: `make shot` where DISPLAY
# answers, the Xvfb recipe where it does not, and ask rather than assume which
# of the two a given session is.
#
# So `make shot` is now `scripts/shot.py`: it runs the real app through the
# real `immapp.run`, counts frames, and grabs with
# `hello_imgui.final_app_window_screenshot()`. One shot takes about 2.3s
# against the 22s per tab the Xvfb path sleeps for, and the window size is a
# flag, which the root-window `xwd` grab could not offer.
#
# `scripts/shot.sh` is kept as `make shot-headless` and is NOT dead weight:
# Xvfb is still the right answer where no display answers, which has been true
# of some sessions on this machine and not of others. Its own header documents
# each link in that chain.
#
# Screenshots are how the invisible-text and numpy-ndarray defects were found.
# Neither was reachable from any test in this tree.
# ---------------------------------------------------------------------------

help:              ## this list
	@echo "advtext targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@echo
	@$(MAKE) --no-print-directory venv-info

venv-info:         ## say which interpreter the other targets will use
	@if [ -x "$(VENV_PY)" ]; then \
	  echo "interpreter: $(VENV_PY)  (this project's own venv)"; \
	else \
	  echo "interpreter: none -- $(VENV_PY) does not exist."; \
	  echo "             Run 'make bootstrap' to build ./.venv (needs network)."; \
	fi

# Needs network. A sandbox that reaches no package index cannot run this
# target, and there is no fallback for that any more: build ./.venv where pip
# can reach an index.
#
# Debian and Ubuntu ship `venv` separately from python3 and the failure is
# opaque, so it is checked for by name rather than left to surface as an
# ensurepip traceback.
# A half-built venv is worse than none, because the guard above is satisfied
# the moment bin/python exists and every other target then runs against an
# interpreter with no pytest in it. So a venv this recipe created is removed again if the install
# fails. One it did *not* create is left alone -- deleting a venv somebody built
# by hand because a network blip failed one install would be its own defect.
bootstrap:         ## create ./.venv and install advtext + dev tools into it
	@command -v python3 >/dev/null 2>&1 || { \
	  echo "python3 is not on PATH."; exit 2; }
	@python3 -c 'import ensurepip' >/dev/null 2>&1 || { \
	  echo "python3 has no 'ensurepip', so it cannot create a virtualenv."; \
	  echo "  Debian/Ubuntu split this out:  sudo apt install python3-venv"; \
	  exit 2; }
	@created=0; \
	if [ ! -d "$(VENV)" ]; then \
	  echo "creating $(VENV)"; \
	  python3 -m venv "$(VENV)" || exit 2; \
	  created=1; \
	fi; \
	if "$(VENV_PY)" -m pip install --upgrade pip setuptools wheel \
	   && "$(VENV_PY)" -m pip install -e ".[dev]"; then \
	  echo; \
	  echo "Done. $(VENV) is now what every target uses -- no edit to this file."; \
	  echo "The editable install also puts advtext on sys.path, so scripts/ runs"; \
	  echo "from any directory rather than only from the repo root."; \
	else \
	  echo; \
	  echo "The install failed. pip needs a package index; run this where one is"; \
	  echo "reachable. Nothing else here can stand in for ./.venv."; \
	  if [ "$$created" = 1 ]; then \
	    rm -rf "$(VENV)"; \
	    echo "Removed the half-built $(VENV) so 'make venv-info' tells the truth."; \
	  fi; \
	  exit 2; \
	fi
	@$(MAKE) --no-print-directory venv-info

test: | $(NEED_VENV) $(NEED_TYPESET) $(NEED_PAIR)  ## pytest (TYPESET=1: with the imtypeset library)
	$(TYPESET_ENV)$(PY) -m pytest -q

lint: | $(NEED_VENV)  ## ruff check + black --check
	$(BIN)ruff check $(SRC)
	$(BIN)black --check $(SRC)

# The only target that writes source files tree-wide, and the only one that can
# cross a task-board file boundary. Several agents write here at once and an
# untracked file reformatted by someone else's run has no revert path, so prefer
# format-file for your own work.
format: | $(NEED_VENV)  ## black, in place, across the whole tree
	$(BIN)black $(SRC)

# The safe path made the easy one. Several files may be given:
# `make format-file FILE="a.py b.py"`.
format-file: | $(NEED_VENV)  ## black, in place, on FILE= only
	@test -n "$(FILE)" || { echo 'usage: make format-file FILE=path/to/file.py'; exit 2; }
	$(BIN)black $(FILE)

typecheck: | $(NEED_VENV)  ## mypy over the package
	$(BIN)mypy advtext

check: lint typecheck test   ## everything the CI gate would run

# The demo that works everywhere: no GPU, no display, no ImGui. This is how the
# litmus tests are shown to have worked rather than merely asserted.
#
# Since 2026-10-11 this target is also the one remaining user of advtext's own
# Python layout core (line breaking, packing, ship-out, the math list): what
# scripts/render_litmus.py and advtext/backends/svg.py import, 22 modules, is
# kept for it and for nothing else. Whether it stays in advtext is a question
# the user has been asked and has not answered (docs/status.md, section 0d).
svg: | $(NEED_VENV)  ## render the litmus artifacts to artifacts/
	PYTHONPATH=$(CURDIR)$${PYTHONPATH:+:$$PYTHONPATH} $(PY) scripts/render_litmus.py --out artifacts

# This target really launches the window, and it is safe to invoke even where
# one cannot open. Two failure modes, neither of which is a hang:
#
#   DISPLAY unset      scripts/run_demo.py refuses and prints what to do instead.
#   DISPLAY unreachable  GLFW fails in about half a second with
#                        `IM_ASSERT( glfwInitSuccess ) --- runner_glfw3.cpp:67`.
#
# An earlier version of this recipe refused to run at all, on the grounds that a
# window here *hangs*. That is true of the xvfb path -- Xvfb cannot create its
# lock file under /tmp in the sandbox and dies silently -- and it is not true of
# a set-but-unreachable DISPLAY, which was measured at 0.6s to a clean
# traceback. Refusing to try cost more than trying.
#
# PYTHONPATH covers an interpreter given as `PY=...` that has the dependencies
# but no editable install of advtext. Under ./.venv, which `make bootstrap`
# installs editable, it is redundant and harmless.
#
# Arguments pass through:  make run ARGS="--source demo/sample.md"
#
# Without TYPESET=1 (or IMTYPESET_LIBRARY) the window opens and every page is
# one line saying the library is not loaded; the script says so on stderr
# first. With it, and a library that was nonetheless not drawing when the
# window closed, the script says why at exit.
run: | $(NEED_VENV) $(NEED_TYPESET) $(NEED_PAIR)  ## launch the ImGui demo (needs a display; TYPESET=1 for its text)
	$(TYPESET_ENV)PYTHONPATH=$(CURDIR)$${PYTHONPATH:+:$$PYTHONPATH} $(PY) scripts/run_demo.py $(ARGS)

# One PNG of the real demo, on the real display. Everything is a flag, because
# the interesting shots are comparisons -- the same tab at two widths, or the
# same document at one, two and three columns:
#
#   make shot
#   make shot ARGS="--tab columns --width 1400 --out artifacts/columns-3.png"
#
# One process per shot rather than a loop inside the script. The grab is
# `final_app_window_screenshot`, which by name and by contract returns the last
# frame of the app that has *exited*, so one app lifetime is one photograph.
#
# With TYPESET=1 a shot whose library was not drawing when the window closed
# exits 3 and writes no PNG (scripts/shot.py, NOT_DRAWN_STATUS), and shot-all
# stops there. Without it the shot is of the one line each page then draws,
# which the script says on stderr.
shot: | $(NEED_VENV) $(NEED_TYPESET) $(NEED_PAIR)  ## screenshot one page of the demo (needs a display; TYPESET=1 for its text; ARGS= passes through)
	$(TYPESET_ENV)PYTHONPATH=$(CURDIR)$${PYTHONPATH:+:$$PYTHONPATH} $(PY) scripts/shot.py $(ARGS)

# The loop stays here rather than moving into the script because one photograph
# needs one app lifetime -- see `shot` above -- so it cannot become a loop inside
# a single process.
#
# The *list* is what went stale, so there is no list here any more. It named
# three tabs for a whole batch after the app grew to five, and `make shot-all`
# then exited 0 having silently skipped Columns and Specimen: a reviewer told to
# use this target would have produced a confident review of the wrong thing,
# with nothing anywhere reporting an omission. The app's pages are now modules
# found by scanning advtext/ui/pages/, and `scripts/shot.py --list` prints the
# requests to photograph -- each page in each state its own PAGE.shots names --
# from that same scan. Adding a page adds its shots; nobody edits this file.
# A page module that cannot be loaded makes --list exit non-zero and this
# target stops there, before the first window, rather than shooting the rest.
# `tests/test_shot_all.py` runs this recipe and holds it to that.
#
# Entries are `scripts/shot.py --tab` requests, not bare names -- `columns:3` is
# the Columns page at three columns and `document:debug` is the Document page
# with the overlay on. The filename is the entry with `:` and `,` flattened to
# `-`, because a colon in a path is legal here and a nuisance everywhere else.
#
# SHOT_TABS is empty by default, which means "ask the app". Set it to shoot a
# subset:  make shot-all SHOT_TABS=document   (or export it; `?=` honours both)
SHOT_TABS ?=

shot-all: | $(NEED_VENV) $(NEED_TYPESET) $(NEED_PAIR)  ## screenshot every page (scripts/shot.py --list) to artifacts/demo-<tab>.png
	@tabs="$(SHOT_TABS)"; \
	if [ -z "$$tabs" ]; then \
	  tabs=$$($(TYPESET_ENV)PYTHONPATH=$(CURDIR)$${PYTHONPATH:+:$$PYTHONPATH} $(PY) scripts/shot.py --list) \
	    || { echo "shot-all: scripts/shot.py --list failed; nothing was photographed" >&2; exit 2; }; \
	  [ -n "$$tabs" ] \
	    || { echo "shot-all: scripts/shot.py --list named no page; nothing was photographed" >&2; exit 2; }; \
	fi; \
	for tab in $$tabs; do \
	  name=$$(printf '%s' "$$tab" | tr ':,' '--'); \
	  $(TYPESET_ENV)PYTHONPATH=$(CURDIR)$${PYTHONPATH:+:$$PYTHONPATH} $(PY) scripts/shot.py \
	    --tab "$$tab" --out "artifacts/demo-$$name.png" $(ARGS) || exit $$?; \
	done

# The fallback for a machine with no display, and the reason it is not the
# default is measured: 22s per tab against 2.3s, and it photographs the X root
# window rather than the app's, so it cannot be asked for a window size.
shot-headless: | $(NEED_VENV)  ## screenshot every tab via an Xvfb in a user namespace
	PY=$(PY) sh scripts/shot.sh artifacts

# A wheel and an sdist a host can name in a requirement (pptmstr's P31).
#
# Of a COMMIT, never of the working tree: scripts/make_dist.py exports HEAD
# (DIST_REV=<rev> for another commit) with `git archive`, twice, builds each
# export with `python -m build --no-isolation` under SOURCE_DATE_EPOCH = the
# commit's time, and installs the pair into DIST_DIR only when the two builds
# are the same bytes and the wheel holds advtext/ and its metadata and nothing
# else. Beside each file goes <file>.sha256, and BUILT-FROM names the commit
# and the tools. It ends by printing the requirement strings: a git reference
# by commit for now, a direct URL with the hash for a release once somebody
# publishes one. Exit 2: it could not start (no `build` or `hatchling` in the
# interpreter -- both are in the dev extra, `make bootstrap`; not a git
# checkout). Exit 3: it built and refused what it built; DIST_DIR is as it was.
#
# It publishes nothing, tags nothing and reaches no network. `-P` because this
# directory has a build/ in it, which `import build` would otherwise find.
#
# NOT RUN with the real builder by the session that wrote it (2026-10-12: no
# `build`, no `hatchling` in ./.venv, no index reachable). tests/test_dist.py
# runs the script end to end against a stand-in builder.
DIST_DIR ?= dist
DIST_REV ?= HEAD

dist: | $(NEED_VENV)  ## build a wheel and an sdist of HEAD (not the working tree) into dist/, twice, with sha256 and requirement strings
	$(PY) -P scripts/make_dist.py --out "$(DIST_DIR)" --rev "$(DIST_REV)" $(ARGS)

clean:             ## remove caches and generated artifacts
	rm -rf .mypy_cache .ruff_cache .pytest_cache dist build artifacts
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
