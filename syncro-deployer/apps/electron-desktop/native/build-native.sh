#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${SCRIPT_DIR}/dist"
mkdir -p "${OUT_DIR}"

OS="$(uname -s)"
CC_BIN="${CC:-gcc}"

if [[ "${OS}" == "Darwin" ]]; then
  TARGET="${OUT_DIR}/libsyncro_native.dylib"
  "${CC_BIN}" -O2 -Wall -Wextra -std=c99 -dynamiclib -fPIC \
    -o "${TARGET}" "${SCRIPT_DIR}/src/syncro_native.c"
else
  TARGET="${OUT_DIR}/libsyncro_native.so"
  "${CC_BIN}" -O2 -Wall -Wextra -std=c99 -shared -fPIC \
    -Wl,-soname,libsyncro_native.so \
    -o "${TARGET}" "${SCRIPT_DIR}/src/syncro_native.c"
fi

echo "Built native shared library: ${TARGET}"
ls -lh "${TARGET}"
