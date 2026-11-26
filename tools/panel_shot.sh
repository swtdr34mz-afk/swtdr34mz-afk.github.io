#!/usr/bin/env bash
# Draws a plugin's panel at 3x as a PNG with the repo's own picture tool, built here:
#   the plugin's snapshot target (-D<NAME>_SNAPSHOT=ON, <Name>Shot) or tools/panel (<x>_panel).
#   panel_shot.sh SRC_DIR OUT.png      (exits 3 when the repo has no picture tool)
set -euo pipefail
SRC=$1; OUT=$(realpath -m "$2"); SCALE=${SCALE:-3}
cd "$SRC"
OPT=$(grep -oE 'option\(([A-Z0-9_]+_SNAPSHOT)' CMakeLists.txt 2>/dev/null | head -1 | sed 's/option(//' || true)
if [ -n "$OPT" ]; then
  TGT=$(grep -oE 'build ([A-Za-z0-9_]+Shot)' CMakeLists.txt | head -1 | awk '{print $2}')
  cmake -S . -B build-shot -G Ninja -DCMAKE_BUILD_TYPE=Release -D$OPT=ON >/dev/null
  cmake --build build-shot --target "$TGT"
  BIN=$(find build-shot -type f -name "$TGT" -perm -u+x | head -1)
elif [ -f tools/panel/CMakeLists.txt ]; then
  cmake -S tools/panel -B build-shot -G Ninja -DCMAKE_BUILD_TYPE=Release >/dev/null
  cmake --build build-shot
  BIN=$(find build-shot -type f -name '*_panel' -perm -u+x | head -1)
else
  echo "no picture tool in this repo"; exit 3
fi
echo "running $BIN"
xvfb-run -a "$BIN" "$OUT" "$SCALE"
ls -la "$OUT"
