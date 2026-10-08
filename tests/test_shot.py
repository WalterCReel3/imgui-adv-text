"""
Tests for `scripts/shot.py`: the PNG encoder, the runner patch, and one shot.

Loaded by path rather than imported, for the reason `tests/test_bench_draw.py`
and `tests/test_verify_advances.py` give at length: `scripts/` must stay off
`sys.path` so no test can import a script by accident and make the suite depend
on collection order.

**On the one skip in this file.** `docs/status.md` values a suite with few
skips, so the gate here is narrow on purpose:
`test_a_real_shot_of_the_real_app_is_a_valid_non_blank_png` takes the `window`
fixture from `tests/conftest.py`, which runs the shot on the session's own
`DISPLAY` when that accepts a connection, on an Xvfb in a user namespace when
it does not, and skips only when neither can be had -- saying which probe
failed.

This file used to argue the opposite: gate on `DISPLAY` being *set*, never on
it being reachable, so that a set-but-broken display went red. That was written
when `DISPLAY=:1` was live on the machine it was written on. In every sandboxed
session since, `DISPLAY=:1` has been set and unreachable (`socket(AF_UNIX)` is
refused), and the test was red for a reason that said nothing about the code.
`tests/conftest.py` records the reversal and what the probe does and does not
guess at.

Everything else runs with no display at all, including the runner patch, which
is driven against a **real `hello_imgui.RunnerParams`** rather than a stub.
Constructing one allocates a C++ struct and opens nothing. That matters: a stub
with the attribute names copied out of the script under test would keep passing
after imgui-bundle renamed `fps_idling.enable_idling`, and a renamed attribute
is the failure this pair of functions is actually exposed to. The stub would
assert that the script agrees with itself.

The orientation of the grab is checked in neither place, and that is a gap
stated rather than hidden. A vertically flipped photograph is still a valid PNG
of the right size with the right number of colours, so no assertion available
here separates it from a correct one. It was checked by reading the image:
`scripts/shot.py::_grab` records what was seen.
"""

from __future__ import annotations

import importlib.util
import socket
import struct
import zlib
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import pytest
from conftest import display_is_reachable

if TYPE_CHECKING:
    from conftest import Window

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "shot.py"


def _load() -> ModuleType:
    """
    Load the script as a module without putting `scripts/` on `sys.path`.
    """
    spec = importlib.util.spec_from_file_location("_shot_under_test", _SCRIPT)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        pytest.fail(f"{_SCRIPT} could not be loaded as a module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


shot = _load()


# ----------------------------------------------------------------------
# The fixture. Every assertion below leans on it being asymmetric.

_WIDTH, _HEIGHT = 5, 3


def _rows() -> list[bytes]:
    """
    A buffer no symmetry can survive: non-square, and every row and column
    distinct.

    This is the load-bearing part of the file rather than the tidy part.
    `test_the_fixture_is_asymmetric_enough_to_catch_a_flip_or_a_transpose`
    exists to keep it honest, because the obvious fixture -- a solid colour, or
    a gradient down the rows only -- round-trips just as happily through an
    encoder that reversed the rows, transposed the image, or swapped R and B.
    `docs/status.md` section 5 is four worked examples of exactly that mistake.

    The channels differ per pixel too (`r` varies with the column, `b` with the
    row, `g` with both), so a BGR-ordered encoder is caught as well as a
    flipped one.
    """
    return [
        bytes(
            byte for x in range(_WIDTH) for byte in (10 + 40 * x, 200 - 7 * x - 11 * y, 3 + 60 * y)
        )
        for y in range(_HEIGHT)
    ]


def _decode_png(blob: bytes) -> tuple[int, int, int, int, list[bytes]]:
    """
    Parse a truecolour PNG back to `(width, height, depth, colour_type, rows)`.

    Every chunk's CRC is recomputed and compared, so a plausible-looking blob
    with a wrong checksum fails here rather than being accepted. Filter type 0
    is required on every row -- this decoder deliberately cannot undo any other
    filter, so an encoder that started emitting one would be caught rather than
    quietly decoded.
    """
    assert blob[:8] == b"\x89PNG\r\n\x1a\n", "missing PNG signature"

    offset, header, idat, seen = 8, b"", b"", []
    while offset < len(blob):
        (length,) = struct.unpack(">I", blob[offset : offset + 4])
        tag = blob[offset + 4 : offset + 8]
        data = blob[offset + 8 : offset + 8 + length]
        (crc,) = struct.unpack(">I", blob[offset + 8 + length : offset + 12 + length])
        assert crc == zlib.crc32(tag + data) & 0xFFFFFFFF, f"bad CRC on {tag!r} chunk"
        seen.append(tag)
        if tag == b"IHDR":
            header = data
        elif tag == b"IDAT":
            idat += data
        offset += 12 + length

    assert seen[0] == b"IHDR" and seen[-1] == b"IEND", f"chunk order is wrong: {seen}"
    width, height, depth, colour_type, _, _, interlace = struct.unpack(">IIBBBBB", header)
    assert interlace == 0, "this decoder does not de-interlace"

    raw = zlib.decompress(idat)
    stride = width * (3 if colour_type == 2 else 0)
    assert len(raw) == height * (stride + 1), "IDAT is not height * (1 filter byte + row)"
    rows = []
    for y in range(height):
        start = y * (stride + 1)
        assert raw[start] == 0, f"row {y} uses filter type {raw[start]}, not 0"
        rows.append(raw[start + 1 : start + 1 + stride])
    return width, height, depth, colour_type, rows


# ----------------------------------------------------------------------
# The encoder


def test_the_fixture_is_asymmetric_enough_to_catch_a_flip_or_a_transpose() -> None:
    """
    Meta-test: the round-trip below only means something if this holds.

    A fixture that quietly went uniform would leave the round-trip passing and
    covering nothing, which is failure family 1 in `docs/status.md` section 5,
    found in this tree by a reviewer reading the fixture instead of the
    assertion. So each symmetry the encoder could accidentally apply is shown
    here to produce a *different* byte string.
    """
    rows = _rows()
    assert _WIDTH != _HEIGHT, "a square buffer cannot catch a width/height swap"
    assert len(set(rows)) == _HEIGHT, "rows must be pairwise distinct to catch a flip"

    columns = [bytes(row[x * 3 + c] for row in rows for c in range(3)) for x in range(_WIDTH)]
    assert len(set(columns)) == _WIDTH, "columns must be pairwise distinct too"

    upright = shot.encode_png(_WIDTH, _HEIGHT, rows)
    assert upright != shot.encode_png(_WIDTH, _HEIGHT, rows[::-1]), "a flip would go unnoticed"

    swapped = [bytes(row[i - i % 3 + (2 - i % 3)] for i in range(len(row))) for row in rows]
    assert upright != shot.encode_png(_WIDTH, _HEIGHT, swapped), "BGR would go unnoticed"


def test_the_encoder_round_trips_every_pixel_and_declares_the_right_header() -> None:
    """
    Encode a known buffer, decode it with `zlib`, and get the same bytes back.
    """
    rows = _rows()
    width, height, depth, colour_type, decoded = _decode_png(shot.encode_png(_WIDTH, _HEIGHT, rows))

    assert (width, height) == (_WIDTH, _HEIGHT)
    assert (depth, colour_type) == (8, 2), "8-bit truecolour, no palette and no alpha"
    assert decoded == rows


def test_the_encoder_refuses_a_buffer_whose_shape_contradicts_its_header() -> None:
    """
    A wrong row count or a short row would otherwise produce a corrupt PNG.

    The failure without this is nasty: `IHDR` would claim a size the `IDAT`
    does not carry, and the file would be written happily and fail in whatever
    viewer opened it, a long way from the code that got the shape wrong.
    """
    rows = _rows()
    with pytest.raises(ValueError, match="expected 3 rows"):
        shot.encode_png(_WIDTH, _HEIGHT, rows[:2])
    with pytest.raises(ValueError, match="must be 15 bytes"):
        shot.encode_png(_WIDTH, _HEIGHT, [row[:-3] for row in rows])


def test_write_png_creates_the_output_directory(tmp_path: Path) -> None:
    """
    `--out artifacts/columns/three.png` must not fail because `columns/` is new.
    """
    out = tmp_path / "does" / "not" / "exist" / "shot.png"
    shot.write_png(out, _WIDTH, _HEIGHT, _rows())
    assert _decode_png(out.read_bytes())[4] == _rows()


# ----------------------------------------------------------------------
# The runner patch, against a real RunnerParams and no window


def _params() -> object:
    """
    A real `hello_imgui.RunnerParams`. Allocates a C++ struct; opens nothing.
    """
    hello_imgui = pytest.importorskip("imgui_bundle.hello_imgui")
    return hello_imgui.RunnerParams()


def test_the_frame_limit_asks_to_exit_exactly_once_on_the_nth_frame() -> None:
    """
    Not before, and -- the part worth testing -- not again afterwards.

    `install_frame_limit` compares `== frames`, and the tempting `>= frames`
    passes any test that only checks "exit was requested by the end". The
    assertion that separates them is the one after the loop has run past `N`.
    """
    runner, exits = _params(), []
    shot.install_frame_limit(runner, 3, lambda: exits.append(len(exits)))

    after_swap = runner.callbacks.after_swap
    assert after_swap is not None, "the patch did not install a callback"

    for _ in range(2):
        after_swap()
    assert exits == [], "exit was requested before the frame count was reached"

    after_swap()
    assert exits == [0], "exit was not requested on the third frame"

    for _ in range(4):
        after_swap()
    assert exits == [0], "exit was requested again on every frame after the third"


def test_the_frame_limit_chains_onto_a_callback_the_app_already_installed() -> None:
    """
    Dropping the app's own `after_swap` would be a silent trap.

    `advtext.ui.app.run` sets none today, so this guards the person who adds the
    first one rather than any behaviour shipping now. Both orderings are pinned:
    the app's callback runs on every frame including the one that exits, so a
    patch that stopped chaining after the limit would also be caught.
    """
    runner, calls, exits = _params(), [], []
    runner.callbacks.after_swap = lambda: calls.append("app")
    shot.install_frame_limit(runner, 2, lambda: exits.append("exit"))

    after_swap = runner.callbacks.after_swap
    after_swap()
    after_swap()
    after_swap()

    assert calls == ["app", "app", "app"], "the app's own after_swap was dropped or skipped"
    assert exits == ["exit"]


def test_the_frame_limit_switches_idling_off() -> None:
    """
    With idling on, `--frames 30` takes wall-clock time, not 30 frames' worth.

    `enable_idling` is asserted to start `True` so the assertion after the call
    is a change rather than a coincidence -- hello_imgui's default is on, and if
    it ever flips to off this test says so instead of passing for free.
    """
    runner = _params()
    assert runner.fps_idling.enable_idling is True, "hello_imgui's default changed"
    shot.install_frame_limit(runner, 1, lambda: None)
    assert runner.fps_idling.enable_idling is False


def test_the_window_size_is_forced_and_remembered_geometry_is_refused() -> None:
    """
    A shot asked for at 1400px must not come back at last week's window width.

    `restore_previous_geometry` is set `True` first on purpose. It defaults to
    `False`, so asserting it is `False` afterwards would pass against a
    `apply_window_size` that never mentioned it -- the third failure family in
    `docs/status.md` section 5, an assertion that holds no matter what the code
    under test does.
    """
    runner = _params()
    runner.app_window_params.restore_previous_geometry = True
    assert list(runner.app_window_params.window_geometry.size) != [1400, 600]

    shot.apply_window_size(runner, 1400, 600)

    assert list(runner.app_window_params.window_geometry.size) == [1400, 600]
    assert runner.app_window_params.restore_previous_geometry is False


def test_a_clamped_window_is_reported_and_a_hidpi_one_is_not() -> None:
    """
    The two ways a photograph can differ from the size asked for, kept apart.

    Silence on the HiDPI case is the assertion that would be easiest to get
    wrong in the useful direction: a `size_warning` that simply compared
    `requested != captured` would pass every clamping test here and then cry
    wolf on every shot taken on a retina display, at which point the warning
    gets ignored and stops working for the case it was written for.

    The clamp is not hypothetical. On this machine's 1920-wide monitor,
    `--width 2400` and `--width 3000` both capture 1920, which is exactly how
    two shots meant to show a reflow come back identical.
    """
    assert shot.size_warning((1400, 600), (1400, 600), 1.0) is None
    assert shot.size_warning((1100, 800), (2200, 1600), 2.0) is None, "HiDPI is not a fault"

    clamped = shot.size_warning((2400, 700), (1920, 700), 1.0)
    assert clamped is not None, "a window clamped to the monitor was not reported"
    assert "2400x700" in clamped and "1920x700" in clamped, "the message hides the numbers"

    scaled_and_clamped = shot.size_warning((2400, 700), (1920, 700), 2.0)
    assert scaled_and_clamped is not None
    assert "scale is 2.0" in scaled_and_clamped, "a scaled mismatch blamed the window manager"


# ----------------------------------------------------------------------
# One real shot. See this file's docstring for why this skip is the exception.


def test_the_display_probe_says_yes_to_a_listener_and_no_to_everything_else() -> None:
    """
    The probe that decides where the real shot runs, against sockets this test owns.

    A wrong "no" only costs a slower window (the shot runs on Xvfb); a wrong
    "yes" would send the shot to a display that is not there, so the "no"
    cases are the ones that matter: a closed port, an unparseable name, and a
    unix display number nothing listens on. The unix-socket "yes" is not
    tested: in the sandbox this was written in `socket(AF_UNIX)` is refused
    outright, so a listener cannot be made.
    """
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        if port >= 6000:
            assert display_is_reachable(f"127.0.0.1:{port - 6000}") is True
            assert display_is_reachable(f"127.0.0.1:{port - 6000}.0") is True
    if port >= 6000:
        assert display_is_reachable(f"127.0.0.1:{port - 6000}", timeout=0.2) is False
    assert display_is_reachable("127.0.0.1:nonsense") is False
    assert display_is_reachable("") is False
    assert display_is_reachable(":59999") is False


def _numpy_is_installed() -> bool:
    """
    Whether this interpreter can receive the screenshot buffer at all.

    Not a stand-in for the script's own numpy check, which is a different claim
    made in a different place and stays under test through the error path
    `scripts/shot.py::_grab` raises. This one decides whether running the shot
    would be measuring the interpreter instead of the code.
    """
    return importlib.util.find_spec("numpy") is not None


@pytest.mark.skipif(
    not _numpy_is_installed(),
    reason="numpy is not installed, so hello_imgui cannot export the framebuffer",
)
def test_a_real_shot_of_the_real_app_is_a_valid_non_blank_png(window: Window) -> None:
    """
    Open the real window, photograph it, and check something was drawn in it.

    Run as a subprocess because the script exits the process it runs in and
    because an ImGui context is global -- `tests/conftest.py` forbids this
    suite from opening a window in-process and that rule is unchanged. Where
    the window opens (the session's display, or an Xvfb with a software
    rasteriser) is the `window` fixture's decision; `window.where` says which.

    **The numpy gate dates from the borrowed interpreter.** The `Makefile` used
    to be able to select a second interpreter, borrowed from a sibling project,
    which had no numpy; under it this test was red before the gate was added.
    That fallback is gone and the project's own `.venv` has numpy as a declared
    dev dependency, so the gate does not fire there. It is kept because a
    missing dependency is a statement about the environment rather than about
    the code, which is `tests/conftest.py`'s reason for `bundled_fonts`.

    The numpy branch of `_grab` was run for real under that interpreter: it
    exits 1 and prints the nanobind message. The message differs between
    builds -- one reads `could not export nanobind::ndarray: No module named
    'numpy'` and another `...: ModuleNotFoundError: No module named 'numpy'` --
    which is why `_grab` matches on the substring `numpy` and not on the
    sentence.

    The claim that earns the skip is **non-blankness**. A window that opened and
    composited nothing, or composited text in the background colour, is the
    defect no other test in this tree can reach: every glyph position would
    still be correct and the whole suite would still be green. Antialiased text
    produces hundreds of distinct greys -- a real shot measures about 1070
    colours -- while an empty window produces a handful, so the threshold has
    two orders of magnitude of margin and does not depend on the theme, the
    tab, or the content. That matters because other tasks in this batch are
    changing all three.

    Not asserted: orientation, which no cheap oracle here can see. See the
    module docstring.
    """
    out = window.out / "shot.png"
    done = window.run(
        [
            str(_SCRIPT),
            "--tab",
            "document",
            "--width",
            "700",
            "--height",
            "500",
            "--frames",
            "10",
            "--out",
            str(out),
        ]
    )
    assert done.returncode == 0, f"shot.py failed on {window.where}:\n{done.stdout}\n{done.stderr}"

    width, height, depth, colour_type, rows = _decode_png(out.read_bytes())
    assert (width, height) == (700, 500), "--width and --height were not honoured"
    assert (depth, colour_type) == (8, 2)

    colours = {row[x * 3 : x * 3 + 3] for row in rows for x in range(width)}
    assert len(colours) > 100, (
        f"only {len(colours)} distinct colours in the frame -- the window opened but "
        "little or nothing was composited into it"
    )
