import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const APP_DIR = path.resolve(__dirname, '..');

test('Electron main and preload enforce contextIsolation, sandbox, and zero nodeIntegration', () => {
  const mainSrc = fs.readFileSync(path.join(APP_DIR, 'electron', 'main.js'), 'utf8');
  const preloadSrc = fs.readFileSync(path.join(APP_DIR, 'electron', 'preload.js'), 'utf8');

  assert.match(mainSrc, /contextIsolation:\s*true/);
  assert.match(mainSrc, /nodeIntegration:\s*false/);
  assert.match(mainSrc, /sandbox:\s*true/);
  assert.match(preloadSrc, /contextBridge\.exposeInMainWorld\('syncroDesktop'/);
});

test('electron-builder.yml configures Windows (.exe), Linux (.AppImage/.tar.gz/.deb/.rpm), macOS (.dmg) and native libs', () => {
  const cfg = fs.readFileSync(path.join(APP_DIR, 'electron-builder.yml'), 'utf8');
  for (const token of ['nsis', 'portable', 'AppImage', 'tar.gz', 'deb', 'rpm', 'dmg', '*.so', '*.dll', '*.dylib']) {
    assert.ok(cfg.includes(token), `electron-builder.yml missing target/resource token: ${token}`);
  }
});

test('Vite renderer production build emits dist/index.html and JS/CSS assets', () => {
  const distIndex = path.join(APP_DIR, 'dist', 'index.html');
  assert.ok(fs.existsSync(distIndex), 'dist/index.html must exist after npm run build');
  const html = fs.readFileSync(distIndex, 'utf8');
  assert.match(html, /Syncro Deployer/);
  assert.match(html, /id="nav-cloud-cli"/);
  assert.match(html, /id="nav-mcp"/);
});

test('Compiled native shared library (.so/.dylib) exports ABI symbols and blocks shell metacharacters', () => {
  const libFile = process.platform === 'darwin' ? 'libsyncro_native.dylib' : 'libsyncro_native.so';
  const libPath = path.join(APP_DIR, 'native', 'dist', libFile);
  if (process.platform === 'win32' || !fs.existsSync(libPath)) {
    return;
  }

  const pyScript = `
import ctypes, json, sys
lib = ctypes.CDLL(sys.argv[1])
lib.syncro_native_version.restype = ctypes.c_char_p
lib.syncro_native_platform.restype = ctypes.c_char_p
lib.syncro_native_guardrail_check.argtypes = [ctypes.c_char_p]
lib.syncro_native_guardrail_check.restype = ctypes.c_int
lib.syncro_native_fnv1a64.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
lib.syncro_native_fnv1a64.restype = ctypes.c_uint64

out = {
  "version": lib.syncro_native_version().decode(),
  "platform": lib.syncro_native_platform().decode(),
  "safe_check": lib.syncro_native_guardrail_check(b"describe-instances"),
  "unsafe_semicolon": lib.syncro_native_guardrail_check(b"list; rm -rf /"),
  "unsafe_subshell": lib.syncro_native_guardrail_check(b"$(whoami)"),
  "hash": lib.syncro_native_fnv1a64(b"syncro-deployer", 15),
}
print(json.dumps(out))
`;
  const raw = execFileSync('python3', ['-c', pyScript, libPath], { encoding: 'utf8' });
  const res = JSON.parse(raw);

  assert.equal(res.version, '0.2.0-syncro-native');
  assert.equal(res.safe_check, 0);
  assert.equal(res.unsafe_semicolon, 1);
  assert.equal(res.unsafe_subshell, 1);
  assert.ok(res.hash > 0);
});
