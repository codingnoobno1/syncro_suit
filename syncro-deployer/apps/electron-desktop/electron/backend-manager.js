'use strict';

const http = require('node:http');
const path = require('node:path');
const fs = require('node:fs');
const { spawn } = require('node:child_process');

/**
 * Probes an existing Syncro Control Plane on :8080 or spawns the local Python
 * Control Plane sidecar cleanly when running as a desktop app.
 */
class BackendManager {
  constructor({ host = '127.0.0.1', port = 8080 } = {}) {
    this.host = host;
    this.port = port;
    this.child = null;
    this.managed = false;
    this.lastStatus = 'unknown';
  }

  get baseUrl() {
    return `http://${this.host}:${this.port}`;
  }

  checkHealth(timeoutMs = 1800) {
    return new Promise((resolve) => {
      const req = http.get(`${this.baseUrl}/api/v1/health`, { timeout: timeoutMs }, (res) => {
        let data = '';
        res.on('data', (chunk) => {
          data += chunk;
        });
        res.on('end', () => {
          if (res.statusCode === 200) {
            try {
              resolve({ healthy: true, payload: JSON.parse(data) });
              return;
            } catch {
              resolve({ healthy: true, payload: null });
              return;
            }
          }
          resolve({ healthy: false, payload: null });
        });
      });
      req.on('error', () => resolve({ healthy: false, payload: null }));
      req.on('timeout', () => {
        req.destroy();
        resolve({ healthy: false, payload: null });
      });
    });
  }

  _resolveControlPlaneBinary() {
    const repoControlPlane = path.resolve(__dirname, '..', '..', '..', 'services', 'control-plane');
    const candidates =
      process.platform === 'win32'
        ? [
            path.join(repoControlPlane, '.venv', 'Scripts', 'syncro.exe'),
            path.join(repoControlPlane, '.venv', 'Scripts', 'aegis.exe'),
          ]
        : [
            path.join(repoControlPlane, '.venv', 'bin', 'syncro'),
            path.join(repoControlPlane, '.venv', 'bin', 'aegis'),
          ];

    for (const bin of candidates) {
      if (fs.existsSync(bin)) {
        return { bin, cwd: repoControlPlane };
      }
    }
    return null;
  }

  async ensureRunning() {
    const probe = await this.checkHealth();
    if (probe.healthy) {
      this.lastStatus = 'external-running';
      return { started: false, healthy: true, managed: false, url: this.baseUrl };
    }

    const located = this._resolveControlPlaneBinary();
    if (!located) {
      this.lastStatus = 'binary-not-found';
      return { started: false, healthy: false, managed: false, url: this.baseUrl };
    }

    this.child = spawn(located.bin, ['server', '--host', this.host, '--port', String(this.port)], {
      cwd: located.cwd,
      stdio: 'pipe',
      windowsHide: true,
    });
    this.managed = true;
    this.lastStatus = 'starting';

    this.child.on('exit', () => {
      this.child = null;
      this.managed = false;
      this.lastStatus = 'stopped';
    });

    for (let attempt = 0; attempt < 20; attempt++) {
      await new Promise((r) => setTimeout(r, 250));
      const check = await this.checkHealth(1000);
      if (check.healthy) {
        this.lastStatus = 'managed-running';
        return { started: true, healthy: true, managed: true, url: this.baseUrl };
      }
    }

    this.lastStatus = 'start-timeout';
    return { started: true, healthy: false, managed: true, url: this.baseUrl };
  }

  stop() {
    if (this.child && !this.child.killed) {
      try {
        this.child.kill('SIGTERM');
      } catch {
        // Ignore termination race
      }
      this.child = null;
      this.managed = false;
    }
  }
}

module.exports = { BackendManager };
