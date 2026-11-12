#!/bin/bash
# Installs what the tests need in Claude Code cloud sessions: numpy, imageio-ffmpeg (ffmpeg binary)
# and certifi from requirements.txt. pywebview (the window) is left out: it needs a desktop and
# doesn't build in the cloud container, and no test imports it.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

pyhashes="$(python3 -I -c 'import sysconfig; print(sysconfig.get_path("purelib"))')/.session-start-syn.sha256"
if ! sha256sum --check --status "$pyhashes" 2>/dev/null; then
  rm -f "$pyhashes"
  grep -v -i '^pywebview' requirements.txt > /tmp/syn-requirements.txt
  python3 -m pip install --quiet --disable-pip-version-check -r /tmp/syn-requirements.txt
  sha256sum .claude/hooks/session-start.sh requirements.txt > "$pyhashes" 2>/dev/null || rm -f "$pyhashes"
fi
