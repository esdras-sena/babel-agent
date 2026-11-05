#!/bin/bash
# Wrapper installed as /usr/bin/babel-agent
set -euo pipefail
export BABEL_AGENT_DATA="${BABEL_AGENT_DATA:-${XDG_DATA_HOME:-$HOME/.local/share}/babel-agent}"
mkdir -p "$BABEL_AGENT_DATA"
APPDIR="/opt/babel-agent"
exec "$APPDIR/BabelAgent" "$@"
