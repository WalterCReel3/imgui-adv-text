"""
For the tests: an imtypeset INSTALLED in site-packages is not there, unless it is asked for.

The tests of what `imscribe.typesetter` finds were written when no imtypeset
could be installed: nothing to find, a stand-in distribution in a temporary
directory, a stand-in package named by the environment, a library that is
named and does not load. One is installed now (2026-10-13, a dependency), and
it would be found before or instead of every one of those: `IMTYPESET_PYTHON`
goes on the END of `sys.path`, behind site-packages, and an installed
imtypeset reads neither variable, so a test that names a library that is not
there would be handed a working one.

While `IMSCRIBE_TEST_NO_INSTALLED_IMTYPESET` is set (`tests/conftest.py` sets
it for the session when a distribution is installed), `hide()` makes an
`imtypeset` package and an `imtypeset` distribution that live in a
site-packages directory invisible to the process **unless `IMTYPESET_LIBRARY`
names the library inside that very package** -- which is how conftest asks
for the installed one. The rule is read at each import, not once. One
anywhere else on the path (a stand-in) is found as it always was.

Two ways in. The pytest process: conftest calls `hide()`. A child: `site`
imports a module named `sitecustomize` from anywhere on the path at start-up,
so a child started with this directory on `PYTHONPATH` runs the last lines of
this file. A child without it is not affected; `IMSCRIBE_NO_TYPESET` (the
product's own switch) is what keeps such a child from LOOKING.
"""

import importlib.machinery
import os
import site
import sys

VARIABLE = "IMSCRIBE_TEST_NO_INSTALLED_IMTYPESET"
LIBRARY = "IMTYPESET_LIBRARY"


def _site_directories():
    found = []
    try:
        found += site.getsitepackages()
    except Exception:  # noqa: BLE001 -- an interpreter without them
        pass
    try:
        found.append(site.getusersitepackages())
    except Exception:  # noqa: BLE001
        pass
    return {os.path.realpath(entry) for entry in found if entry}


class NotInSitePackages:
    """
    A finder, first on `sys.meta_path`: `imtypeset` is looked for everywhere but site-packages.
    """

    def __init__(self):
        self.sites = _site_directories()

    def hiding(self):
        """Whether the installed one is hidden at this moment: the rule of the module docstring."""
        if not os.environ.get(VARIABLE):
            return False
        named = os.environ.get(LIBRARY) or ""
        if not named:
            return True
        package = os.path.dirname(os.path.realpath(named))
        asked_for = (
            os.path.basename(package) == "imtypeset" and os.path.dirname(package) in self.sites
        )
        return not asked_for

    def find_spec(self, name, path=None, target=None):
        if name != "imtypeset" or not self.hiding():
            return None
        kept = [entry for entry in sys.path if os.path.realpath(entry or ".") not in self.sites]
        spec = importlib.machinery.PathFinder.find_spec(name, kept)
        if spec is None:
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return spec


def hide():
    """
    Install the rule in this process. Once: a second call does nothing.
    """
    from importlib import metadata

    if any(isinstance(finder, NotInSitePackages) for finder in sys.meta_path):
        return
    finder = NotInSitePackages()
    search = metadata.MetadataPathFinder.__dict__["find_distributions"].__func__

    def find_distributions(cls, *args, **kwargs):
        for distribution in search(cls, *args, **kwargs):
            if finder.hiding():
                try:
                    name = (distribution.metadata["Name"] or "").lower()
                    where = os.path.realpath(str(distribution.locate_file("")))
                except Exception:  # noqa: BLE001 -- unreadable: not ours to hide
                    name, where = "", ""
                if name == "imtypeset" and where in finder.sites:
                    continue
            yield distribution

    metadata.MetadataPathFinder.find_distributions = classmethod(find_distributions)
    sys.meta_path.insert(0, finder)


if os.environ.get(VARIABLE):
    hide()
