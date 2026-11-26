#!/bin/sh
# Refresh the Wraith app's local OpenCode service password without storing it in the repo.
set -eu

SRC="${HOME}/.config/opencode/service.json"
APP_FILES="${APP_FILES:-/proc/1/root/data/data/com.wraith.agent/files}"
DEST="${APP_FILES}/opencode_auth.json"

python3 - "$SRC" "$DEST" <<'PY'
import json
import os
import sys

src, dest = sys.argv[1], sys.argv[2]
with open(src, "r", encoding="utf-8") as handle:
    password = json.load(handle)["password"]
with open(dest, "w", encoding="utf-8") as handle:
    json.dump({"password": password}, handle)
os.chmod(dest, 0o600)
PY

uid=$(stat -c '%u' "$APP_FILES")
gid=$(stat -c '%g' "$APP_FILES")
chown "$uid:$gid" "$DEST"
echo "refreshed $DEST"
