#!/bin/sh
# Superseded by `make bootstrap`; kept one release for anyone with it in a script.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
python3 -m venv "$here/.venv"
"$here/.venv/bin/pip" install --quiet --editable "$here[dev]"
echo "environment ready in $here/.venv"
