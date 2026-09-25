#!/bin/sh
# Photograph the ImGui demo without a display, one PNG per tab.
#
# THE FALLBACK, NOT THE PATH. `make shot-headless` runs this; `make shot` runs
# scripts/shot.py, which is the one to reach for. This machine *has* a display
# -- DISPLAY=:1 is live and a window opens on it in about half a second -- so
# the whole apparatus below is unnecessary here, at 22s per tab against 2.3s,
# and it photographs the X root window rather than the app's, so it cannot be
# asked for a window size. It is kept because Xvfb remains the right answer on
# a machine that genuinely has no display.
#
# Two claims in the chain below were true of an earlier sandbox and are false
# here. They are corrected in place rather than deleted, because the mechanism
# still works and a reader on a locked-down box may need the reasoning:
#
#   AF_UNIX is NOT blocked here. socket(AF_UNIX) connects to /tmp/.X11-unix/X1.
#   -listen tcp is retained because it is harmless and because the tmpfs below
#   shadows /tmp/.X11-unix, but it is no longer a workaround for a blocked
#   socket family.
#
#   numpy IS installed, as a dev dependency in pyproject.toml, so hello_imgui's
#   final_app_window_screenshot() works and scripts/shot.py uses it. cv2 is not
#   needed by that call and never was.
#
# The chain that works, and why each link is needed:
#
#   unshare -r    a user namespace where we are root. Xvfb's -nolock is refused
#                 for non-root ("the -nolock option can only be used by root"),
#                 and without it Xvfb insists on a lock file under /tmp.
#   unshare -m    a mount namespace, so the tmpfs below is private and does not
#                 touch the real /tmp.
#   mount tmpfs   /tmp is not writable in the sandbox, which is the single
#                 reason Xvfb would not start. A fresh tmpfs over it gives Xvfb
#                 somewhere for its lock file and its socket directory.
#   -listen tcp   the X connection goes over TCP, hence DISPLAY=127.0.0.1:99
#                 rather than :99, which would resolve to a unix socket under
#                 the tmpfs mounted above. (An earlier note here said AF_UNIX
#                 was blocked outright; see the correction at the top.)
#   llvmpipe      no GPU. Mesa's software rasteriser gives the OpenGL 3.3 core
#                 context GLFW asks for. This is where the 22s per tab goes.
#   xwd           the screenshot: the X server's root window is photographed.
#                 scripts/shot.py grabs the app's own framebuffer instead and
#                 is better in every way that does not involve Xvfb.
#
# The tmpfs shadows $TMPDIR, so nothing written there before entering the
# namespace is visible inside it. Output therefore goes to the repository, which
# is a real path and is not shadowed.
#
# Usage: scripts/shot.sh [output-directory]   (default: artifacts)

set -eu

OUT="${1:-artifacts}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PY:-$ROOT/.venv/bin/python}"
[ -x "$PY" ] || PY=/home/wreel/Source/pptmstr/.venv/bin/python

command -v Xvfb >/dev/null || { echo "Xvfb is not installed (apt install xvfb)"; exit 2; }
command -v xwd  >/dev/null || { echo "xwd is not installed (apt install x11-apps)"; exit 2; }
command -v convert >/dev/null || { echo "convert is not installed (apt install imagemagick)"; exit 2; }
command -v unshare >/dev/null || { echo "unshare is not installed (apt install util-linux)"; exit 2; }

mkdir -p "$ROOT/$OUT"

# Everything past this point runs inside the namespace: the tmpfs, and therefore
# the X server, do not exist outside it.
exec unshare -rm sh -e -c '
ROOT="'"$ROOT"'"; OUT="'"$OUT"'"; PY="'"$PY"'"

mount -t tmpfs tmpfs /tmp
mkdir -p /tmp/.X11-unix /tmp/cache

Xvfb :99 -screen 0 1400x1000x24 -listen tcp >/tmp/xvfb.log 2>&1 &
XVFB=$!
sleep 4
kill -0 $XVFB 2>/dev/null || { echo "Xvfb did not start:"; cat /tmp/xvfb.log; exit 1; }

export DISPLAY=127.0.0.1:99
export LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe
export XDG_CACHE_HOME=/tmp/cache

cd "$ROOT"
STATUS=0
for TAB in document formula blocks; do
    "$PY" scripts/run_demo.py --tab "$TAB" >"/tmp/demo-$TAB.log" 2>&1 &
    DEMO=$!
    # Long enough for the atlas to bake and the document to compose. Composition
    # is tens of milliseconds; baking Latin Modern Math is the slow part.
    sleep 22
    if kill -0 $DEMO 2>/dev/null; then
        xwd -root -display "$DISPLAY" -silent > /tmp/shot.xwd
        convert /tmp/shot.xwd "$OUT/demo-$TAB.png"
        echo "$OUT/demo-$TAB.png"
    else
        echo "the demo exited before it could be photographed ($TAB):"
        tail -12 "/tmp/demo-$TAB.log"
        STATUS=1
    fi
    kill $DEMO 2>/dev/null || true
    sleep 2
done

kill $XVFB 2>/dev/null || true
exit $STATUS
'
