'use strict';

const fs = require('node:fs');
const path = require('node:path');

/**
 * Resolves the bundled platform-specific native shared library (.so / .dll / .dylib)
 * across both development checkouts and packaged electron-builder resources.
 */
function resolveNativeLibraryPath() {
  const libName =
    process.platform === 'win32'
      ? 'syncro_native.dll'
      : process.platform === 'darwin'
        ? 'libsyncro_native.dylib'
        : 'libsyncro_native.so';

  const candidates = [
    process.resourcesPath ? path.join(process.resourcesPath, 'native', libName) : null,
    path.resolve(__dirname, '..', 'native', 'dist', libName),
  ].filter(Boolean);

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return {
        found: true,
        fileName: libName,
        path: candidate,
        sizeBytes: fs.statSync(candidate).size,
        platform: process.platform,
        arch: process.arch,
      };
    }
  }

  return {
    found: false,
    fileName: libName,
    path: candidates[0] || null,
    sizeBytes: 0,
    platform: process.platform,
    arch: process.arch,
  };
}

module.exports = { resolveNativeLibraryPath };
