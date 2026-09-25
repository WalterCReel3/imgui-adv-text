.PHONY: help bootstrap venv-info test lint format format-file typecheck check svg run \
        shot shot-all shot-headless clean

# ---------------------------------------------------------------------------
# Which interpreter runs everything
#
# `make bootstrap` builds ./.venv and every target below picks it up
# automatically, with no edit to this file. Until it exists there is a
# fallback: a *borrowed* interpreter from a sibling project that happens to
# have the same dependencies installed. The fallback is what let this project
# be built at all -- the sandbox reaches only api.anthropic.com, so `pip
# install` cannot run in it and a virtualenv cannot be created there.
#
# The borrowed tree is READ-ONLY. Nothing in this project may write under it.
# It is also not a dependency declaration: pyproject.toml is. The borrowed
# venv's versions run far ahead of pyproject's floors (mypy 2.3 against a
# >=1.11 floor, black 26.5 against >=24.1), so `make bootstrap` may install
# *older* tools than the fallback and surface different lint or type errors.
# That is the floors being honoured rather than anything breaking.
VENV      ?= .venv
VENV_PY   := $(VENV)/bin/python
BORROWED  := /home/wreel/Source/pptmstr/.venv/bin/python
PY        := $(shell test -x $(VENV_PY) && echo $(VENV_PY) || echo $(BORROWED))
BIN       := $(dir $(PY))

# scripts/ does not exist yet and `ruff check` fails on a path that is absent,
# so it joins the set when the first script lands rather than on a later edit.
SRC := advtext tests $(wildcard scripts)

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
# documents. The third, and the one measured rather than inferred:
#
#   DISPLAY=:1 is live and a real window opens on it in about half a second.
#   No Xvfb, no namespace, no software rasteriser.
#
# Two claims that justified the namespace are also false here and were checked
# individually rather than assumed to fall with it:
#
#   "AF_UNIX sockets are blocked"   they are not. socket(AF_UNIX) connects to
#                                   /tmp/.X11-unix/X1, which is how DISPLAY=:1
#                                   works at all.
#   "numpy cannot be installed"     it is installed, as a dev dependency, which
#                                   is what makes hello_imgui's own screenshot
#                                   call usable. cv2 is not needed by it.
#
# So `make shot` is now `scripts/shot.py`: it runs the real app through the
# real `immapp.run`, counts frames, and grabs with
# `hello_imgui.final_app_window_screenshot()`. One shot takes about 2.3s
# against the 22s per tab the Xvfb path sleeps for, and the window size is a
# flag, which the root-window `xwd` grab could not offer.
#
# `scripts/shot.sh` is kept as `make shot-headless` and is NOT dead weight:
# Xvfb is still the right answer on a machine with no display, which this
# machine happens not to be. Its own header documents each link in that chain.
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
	  echo "interpreter: $(BORROWED)"; \
	  echo "             ^ BORROWED from a sibling project, read-only."; \
	  echo "             Run 'make bootstrap' to build ./.venv and use that instead."; \
	fi

# Needs network. The sandbox this project was built in reaches only
# api.anthropic.com, so this target cannot run there and that is the single
# reason the borrowed interpreter above exists.
#
# Debian and Ubuntu ship `venv` separately from python3 and the failure is
# opaque, so it is checked for by name rather than left to surface as an
# ensurepip traceback.
# A half-built venv is worse than none, because $(PY) prefers it the moment the
# directory exists and every other target then runs against an interpreter with
# no pytest in it. So a venv this recipe created is removed again if the install
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
	  echo "The install failed. pip needs an index, and the sandbox this project was"; \
	  echo "built in reaches only api.anthropic.com -- that is the whole reason the"; \
	  echo "borrowed interpreter exists. See 'make venv-info'."; \
	  if [ "$$created" = 1 ]; then \
	    rm -rf "$(VENV)"; \
	    echo "Removed the half-built $(VENV) so the other targets keep working."; \
	  fi; \
	  exit 2; \
	fi
	@$(MAKE) --no-print-directory venv-info

test:              ## pytest
	$(PY) -m pytest -q

lint:              ## ruff check + black --check
	$(BIN)ruff check $(SRC)
	$(BIN)black --check $(SRC)

# The only target that writes source files tree-wide, and the only one that can
# cross a task-board file boundary. Several agents write here at once and an
# untracked file reformatted by someone else's run has no revert path, so prefer
# format-file for your own work.
format:            ## black, in place, across the whole tree
	$(BIN)black $(SRC)

# The safe path made the easy one. Several files may be given:
# `make format-file FILE="a.py b.py"`.
format-file:       ## black, in place, on FILE= only
	@test -n "$(FILE)" || { echo 'usage: make format-file FILE=path/to/file.py'; exit 2; }
	$(BIN)black $(FILE)

typecheck:         ## mypy over the package
	$(BIN)mypy advtext

check: lint typecheck test   ## everything the CI gate would run

# The demo that works everywhere: no GPU, no display, no ImGui. This is how the
# litmus tests are shown to have worked rather than merely asserted.
svg:               ## render the litmus artifacts to artifacts/
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
# PYTHONPATH covers the case where `make bootstrap` has not been run, so the
# demo works against the borrowed interpreter too. After an editable install it
# is redundant and harmless.
#
# Arguments pass through:  make run ARGS="--source demo/sample.md"
run:               ## launch the ImGui demo (needs a display; fails fast without one)
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
shot:              ## screenshot one tab of the demo (needs a display; ARGS= passes through)
	PYTHONPATH=$(CURDIR)$${PYTHONPATH:+:$$PYTHONPATH} $(PY) scripts/shot.py $(ARGS)

# The loop stays here rather than moving into the script because one photograph
# needs one app lifetime -- see `shot` above -- so it cannot become a loop inside
# a single process.
#
# The *list* is what went stale. It named three tabs for a whole batch after the
# app grew to five, and `make shot-all` then exited 0 having silently skipped
# Columns and Specimen: a reviewer told to use this target would have produced a
# confident review of the wrong thing, with nothing anywhere reporting an
# omission. `tests/test_shot_all.py` compares this list against the tab names
# `advtext.ui.app.App.gui` actually draws, and against what the recipe below
# expands to, so the next drift is a red test rather than a missing PNG.
#
# Entries are `scripts/shot.py --tab` requests, not bare names, so a tab's
# interesting states can be listed too -- `columns:3` is the Columns tab at three
# columns and `document:debug` is the Document tab with the overlay on. The
# filename is the entry with `:` and `,` flattened to `-`, because a colon in a
# path is legal here and a nuisance everywhere else.
#
# Override it to shoot a subset:  make shot-all SHOT_TABS=document
SHOT_TABS ?= document document:debug columns:1 columns:2 columns:3 \
             specimen formula blocks

shot-all:          ## screenshot every tab in SHOT_TABS to artifacts/demo-<tab>.png
	@for tab in $(SHOT_TABS); do \
	  name=$$(printf '%s' "$$tab" | tr ':,' '--'); \
	  PYTHONPATH=$(CURDIR)$${PYTHONPATH:+:$$PYTHONPATH} $(PY) scripts/shot.py \
	    --tab "$$tab" --out "artifacts/demo-$$name.png" $(ARGS) || exit $$?; \
	done

# The fallback for a machine with no display, and the reason it is not the
# default is measured: 22s per tab against 2.3s, and it photographs the X root
# window rather than the app's, so it cannot be asked for a window size.
shot-headless:     ## screenshot every tab via an Xvfb in a user namespace
	sh scripts/shot.sh artifacts

clean:             ## remove caches and generated artifacts
	rm -rf .mypy_cache .ruff_cache .pytest_cache dist build artifacts
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
