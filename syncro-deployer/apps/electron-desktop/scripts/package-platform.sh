#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${APP_DIR}"

OS="$(uname -s)"
ARCH="$(uname -m)"
VERSION="$(node -p "require('./package.json').version")"

echo "==> [1/5] Compiling native shared library (${OS}/${ARCH})..."
bash native/build-native.sh

echo "==> [2/5] Generating application icons and building Vite renderer..."
npm run build

echo "==> [3/5] Running Electron desktop & native library smoke tests..."
npm test

echo "==> [4/5] Packaging with electron-builder..."
mkdir -p release
if [[ "${SKIP_ELECTRON_BUILDER:-0}" == "1" ]]; then
  echo "SKIP_ELECTRON_BUILDER=1 — skipping Electron binary bundling; creating portable dist + native .so/.dylib tarball."
elif [[ "${OS}" == "Darwin" ]]; then
  npx electron-builder --mac dmg zip --publish never
else
  npx electron-builder --linux AppImage tar.gz deb rpm --publish never
fi

echo "==> [5/5] Creating standalone native + renderer platform bundle (.tar.gz) & SHA256SUMS..."
BUNDLE_DIR="release/syncro-deployer-bundle-${OS,,}-${ARCH}"
rm -rf "${BUNDLE_DIR}"
mkdir -p "${BUNDLE_DIR}/native" "${BUNDLE_DIR}/renderer" "${BUNDLE_DIR}/electron"
cp -r dist/* "${BUNDLE_DIR}/renderer/"
cp -r electron/* "${BUNDLE_DIR}/electron/"
cp -r native/dist/* "${BUNDLE_DIR}/native/"
cp package.json electron-builder.yml "${BUNDLE_DIR}/"

TAR_NAME="syncro-deployer-${VERSION}-${OS,,}-${ARCH}-bundle.tar.gz"
tar -czf "release/${TAR_NAME}" -C release "$(basename "${BUNDLE_DIR}")"
rm -rf "${BUNDLE_DIR}"

# Also copy standalone native shared library directly into release/ for direct artifact publishing
cp native/dist/* release/

(
  cd release
  sha256sum *.tar.gz *.AppImage *.deb *.rpm *.dmg *.zip *.so *.dylib 2>/dev/null > SHA256SUMS.txt || true
)

echo "==> Release artifacts ready in ${APP_DIR}/release:"
ls -lh release/
