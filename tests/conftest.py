"""
Shared fixtures. There is exactly one, and it earns its file.

Every metrics test needs the directory imgui-bundle ships its fonts in. That
path is long, environment-derived, and wrong to write down: it lives inside
whichever site-packages the interpreter happens to be, and this project runs on
a *borrowed* interpreter under another user's home directory. A test that
hard-codes it encodes somebody's home directory into the suite and breaks the
moment a real virtualenv can be built. The one hard-coded path in this project
is the `PY` line in the Makefile, which is where the seam belongs.

So the fixture resolves the directory the way production code must: import
`imgui_bundle` and walk from its `__file__`. That also makes the fixture a
standing check that the two agree -- if `advtext.fontlib` ever resolves fonts
some other way, the tests stop exercising the path production uses.

Skipping rather than failing when the directory is absent is deliberate. A
missing font directory is a statement about the environment, not about the code
under test, and a red suite that means "wrong machine" trains people to ignore
red suites.

Deliberately not here: an ImGui context fixture. Nothing in this suite may open
a window -- see `docs/decisions.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def bundled_fonts() -> Path:
    """
    The directory imgui-bundle ships Roboto, Inconsolata and Latin Modern Math in.
    """
    try:
        import imgui_bundle
    except ImportError as exc:  # pragma: no cover - environment, not logic
        pytest.skip(f"imgui-bundle is not importable, so its bundled fonts are unreachable: {exc}")

    fonts = Path(imgui_bundle.__file__).parent / "assets" / "fonts"
    if not fonts.is_dir():
        pytest.skip(f"imgui-bundle is installed but ships no font directory at {fonts}")
    return fonts
