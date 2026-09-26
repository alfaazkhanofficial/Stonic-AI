const { spawn } = require('node:child_process');
const { randomBytes } = require('node:crypto');
const { existsSync } = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const http = require('node:http');

const root = path.resolve(__dirname, '..');

function availablePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
  });
}

function frontendEnvironment(env) {
  const result = { ...env };
  for (const key of Object.keys(result)) {
    if (/(?:API_)?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL/i.test(key) && key !== 'STONIC_API_TOKEN') {
      delete result[key];
    }
  }
  return result;
}

function checkStatus(port, token) {
  return new Promise((resolve, reject) => {
    const req = http.request({
      family: 4, 
      hostname: '127.0.0.1',
      port: port,
      path: '/api/status',
      method: 'GET',
      headers: { 'X-Stonic-Token': token },
      timeout: 1000
    }, res => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          try { resolve(JSON.parse(body)); } catch { resolve(true); }
        } else {
          reject(new Error(`HTTP ${res.statusCode}`));
        }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('Timeout')); });
    req.end();
  });
}

function startBackend(port, onStage = () => {}, options = {}) {
  const venvPython = path.join(
    root,
    '.venv',
    process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'
  );
  const bundledPython = path.join(root, 'runtime', 'python', 'python.exe');

  const python = existsSync(venvPython)
    ? venvPython
    : (process.env.STONIC_PYTHON || (existsSync(bundledPython) ? bundledPython : 'python'));

  if (!existsSync(python)) throw new Error('Python missing. Run Setup-Stonic.cmd first.');

  const token = randomBytes(32).toString('hex');
  const dataDir = path.resolve(options.dataDir || process.env.STONIC_DATA_DIR || path.join(root, 'data'));
  const env = frontendEnvironment(process.env);

  env.STONIC_PORT = String(port);
  env.STONIC_HOST = '127.0.0.1';
  env.STONIC_API_TOKEN = token;
  env.STONIC_MANAGED = '1';
  env.PYTHONUTF8 = '1';
  env.PYTHONUNBUFFERED = '1';
  env.STONIC_DATA_DIR = dataDir;

  const child = spawn(
    python,
    ['-m', 'stonic.app', '--port', String(port), '--host', '127.0.0.1'],
    {
      cwd: root,
      env,
      windowsHide: false,
      // 'ignore' severs the stdin pipe, preventing GIL deadlocks
      // while allowing Python to use the ProactorEventLoop required for subprocesses.
      stdio: ['ignore', 'pipe', 'pipe'] 
    }
  );

  let buffer = '', failure = '';

  child.stderr.on('data', data => {
    process.stderr.write(data);
    failure = (failure + data.toString()).slice(-6000);
  });

  child.stdout.on('data', data => {
    process.stdout.write(data);
    buffer += data.toString();
    let newline;
    while ((newline = buffer.indexOf('\n')) !== -1) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (line.startsWith('STONIC_STAGE:')) {
        try { onStage(JSON.parse(line.slice(13)).message); } catch {}
      }
    }
  });

  child.on('error', error => { failure = error.message; });

  async function ready() {
    const deadline = Date.now() + 180000; 
    let lastError = '';
    while (Date.now() < deadline) {
      if (child.exitCode !== null) throw new Error(failure || `Exited with code ${child.exitCode}`);
      try {
        const res = await checkStatus(port, token);
        if (res) return res;
      } catch (e) {
        lastError = e.message;
      }
      await new Promise(r => setTimeout(r, 500));
    }
    throw new Error(failure || `The local service did not become ready within 180 seconds. Last error: ${lastError}`);
  }

  async function stop() {
    if (child.exitCode !== null) return;
    child.kill(); 
  }

  return { child, env, frontendEnv: frontendEnvironment(env), token, ready, stop, port, root, dataDir };
}

module.exports = { startBackend, availablePort, root, frontendEnvironment };