"""
The package is `imscribe`. Until 2026-10-12 it was `advtext`.

The user's decision, their words: "I'm really tempted by 'imscribe' as it is a
phonetic sound-a-like to 'inscribe' the word." It was a rename and nothing
else: no signature and no behaviour changed with it (`docs/decisions.md`,
"The package is renamed imscribe").

**No alias was left behind**, on purpose: nothing was published under the old
name, and a package that exists only to forward to another is code written to
be deleted. So the old name must not import, and the one test here says so.
What it guards against is the directory coming back by accident: a branch
from before the rename merged without care, a file restored into `advtext/`,
a shim somebody adds for one caller. Any of those makes two packages of one
tree, and the half of a host that still imports the old one then runs
modules that nothing gates.

This file is the one place under `tests/` where the old word is the old
package's name on purpose; `.concerns/RENAME-scripts/rename.py` leaves it
alone.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_OLD = "advtext"


def test_the_old_name_is_not_a_package_and_importing_it_is_an_error() -> None:
    """
    No `advtext/` beside `imscribe/`, and `import advtext` raises.

    Both halves, because each fails alone: a directory with no `__init__.py`
    still imports (as a namespace package), and a module of that name
    installed somewhere else on the path imports with no directory here.
    """
    assert (_ROOT / "imscribe" / "__init__.py").is_file()
    assert not (_ROOT / _OLD).exists(), f"{_OLD}/ is back beside imscribe/"
    with pytest.raises(ModuleNotFoundError) as raised:
        importlib.import_module(_OLD)
    assert raised.value.name == _OLD
