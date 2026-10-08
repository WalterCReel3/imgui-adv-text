.PHONY: help bootstrap venv-info test lint format format-file typecheck check svg run \
        shot shot-all shot-headless clean

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

test: | $(NEED_VENV)  ## pytest
	$(PY) -m pytest -q

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
run: | $(NEED_VENV)  ## launch the ImGui demo (needs a display; fails fast without one)
	PYTHONPATH=$(CURDIR)$${PYTHONPATH:+:$$PYTHONPATH} $(PY) scripts/run_demo.py $(ARGS)

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
shot: | $(NEED_VENV)  ## screenshot one page of the demo (needs a display; ARGS= passes through)
	PYTHONPATH=$(CURDIR)$${PYTHONPATH:+:$$PYTHONPATH} $(PY) scripts/shot.py $(ARGS)

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

shot-all: | $(NEED_VENV)  ## screenshot every page (scripts/shot.py --list) to artifacts/demo-<tab>.png
	@tabs="$(SHOT_TABS)"; \
	if [ -z "$$tabs" ]; then \
	  tabs=$$(PYTHONPATH=$(CURDIR)$${PYTHONPATH:+:$$PYTHONPATH} $(PY) scripts/shot.py --list) \
	    || { echo "shot-all: scripts/shot.py --list failed; nothing was photographed" >&2; exit 2; }; \
	  [ -n "$$tabs" ] \
	    || { echo "shot-all: scripts/shot.py --list named no page; nothing was photographed" >&2; exit 2; }; \
	fi; \
	for tab in $$tabs; do \
	  name=$$(printf '%s' "$$tab" | tr ':,' '--'); \
	  PYTHONPATH=$(CURDIR)$${PYTHONPATH:+:$$PYTHONPATH} $(PY) scripts/shot.py \
	    --tab "$$tab" --out "artifacts/demo-$$name.png" $(ARGS) || exit $$?; \
	done

# The fallback for a machine with no display, and the reason it is not the
# default is measured: 22s per tab against 2.3s, and it photographs the X root
# window rather than the app's, so it cannot be asked for a window size.
shot-headless: | $(NEED_VENV)  ## screenshot every tab via an Xvfb in a user namespace
	PY=$(PY) sh scripts/shot.sh artifacts

clean:             ## remove caches and generated artifacts
	rm -rf .mypy_cache .ruff_cache .pytest_cache dist build artifacts
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
