#!/usr/bin/env bash
# The fleet's Mac, brought up without an administrator: Alloy for its vitals and Ollama as
# its engine, each a user launch agent from the vendor's own release archive
# (docs/compute-fleet.md § Joining a node). Nothing here needs sudo, Homebrew or Docker; the
# Mac was not to be reset and has none of them.
#
#   bash ~/docket-yard/tools/fleet/mac-up.sh              # install or update both, and start
#   launchctl list | grep docketyard                      # the two agents
#   tail -f ~/docketyard/logs/alloy.log ~/docketyard/logs/ollama.log
#
# DY_FLEET_DATA is the data root (default ~/docketyard); `<root>/alloy.env` holds the Grafana
# credentials and FLEET_HOST. Ollama listens on the LAN (OLLAMA_HOST=0.0.0.0) as vLLM does on
# the GPU boxes; the LAN is the operator's. Models are pulled when a pass needs one — an engine
# with no model is the point of "ready".

set -eu
DATA=${DY_FLEET_DATA:-$HOME/docketyard}
ALLOY_VERSION=${ALLOY_VERSION:-v1.10.0}
OLLAMA_VERSION=${OLLAMA_VERSION:-v0.34.0}
BIN=$DATA/bin
LOG=$DATA/logs
AGENTS=$HOME/Library/LaunchAgents
mkdir -p "$BIN" "$LOG" "$DATA/alloy" "$AGENTS"

if [ ! -x "$BIN/alloy" ] || ! "$BIN/alloy" --version 2>/dev/null | grep -q "${ALLOY_VERSION#v}"; then
    echo "alloy $ALLOY_VERSION"
    curl -fsSL -o /tmp/alloy.zip \
        "https://github.com/grafana/alloy/releases/download/$ALLOY_VERSION/alloy-darwin-arm64.zip"
    unzip -qo /tmp/alloy.zip -d /tmp/alloy && mv /tmp/alloy/alloy-darwin-arm64 "$BIN/alloy"
    chmod +x "$BIN/alloy"; rm -rf /tmp/alloy /tmp/alloy.zip
fi
# the archive is the binary AND lib/ollama beside it — the Metal runtime and llama-server —
# so it is installed whole; the binary finds its runtime relative to itself
OLLAMA=$DATA/ollama-dist/ollama
if [ ! -x "$OLLAMA" ] || ! "$OLLAMA" --version 2>/dev/null | grep -q "${OLLAMA_VERSION#v}"; then
    echo "ollama $OLLAMA_VERSION"
    curl -fsSL -o /tmp/ollama.tgz         "https://github.com/ollama/ollama/releases/download/$OLLAMA_VERSION/ollama-darwin.tgz"
    rm -rf "$DATA/ollama-dist" && mkdir -p "$DATA/ollama-dist"
    tar -xzf /tmp/ollama.tgz -C "$DATA/ollama-dist"; rm -f /tmp/ollama.tgz
    chmod +x "$OLLAMA"
fi
ln -sf "$OLLAMA" "$BIN/ollama"

# a wrapper per agent: launchd cannot source an env file, a shell can
cat > "$BIN/run-alloy.sh" <<EOF
#!/bin/sh
set -a; . "$DATA/alloy.env"; set +a
exec "$BIN/alloy" run --storage.path="$DATA/alloy" "$HOME/docket-yard/tools/fleet/config-mac.alloy"
EOF
cat > "$BIN/run-ollama.sh" <<EOF
#!/bin/sh
export OLLAMA_HOST=0.0.0.0:11434 OLLAMA_MODELS="$DATA/models"
exec "$OLLAMA" serve
EOF
chmod +x "$BIN/run-alloy.sh" "$BIN/run-ollama.sh"

agent() {  # agent <label> <wrapper> <log>
    local plist=$AGENTS/$1.plist
    cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$1</string>
  <key>ProgramArguments</key><array><string>$2</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$3</string>
  <key>StandardErrorPath</key><string>$3</string>
</dict></plist>
EOF
    launchctl bootout "gui/$(id -u)/$1" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$plist"
    echo "$1: started"
}
agent org.docketyard.alloy "$BIN/run-alloy.sh" "$LOG/alloy.log"
agent org.docketyard.ollama "$BIN/run-ollama.sh" "$LOG/ollama.log"
