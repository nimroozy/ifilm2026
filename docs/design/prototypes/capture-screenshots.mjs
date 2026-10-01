#!/usr/bin/env node
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync, copyFileSync, existsSync, createReadStream, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import http from 'node:http';

const __dirname = dirname(fileURLToPath(import.meta.url));
const outDir = join(__dirname, '..', 'screenshots');
const artifactDir = '/opt/cursor/artifacts/customer-ui-v2-g0';
mkdirSync(outDir, { recursive: true });
mkdirSync(artifactDir, { recursive: true });

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.png': 'image/png',
};

function startServer(root, port = 8765) {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      const url = new URL(req.url, `http://127.0.0.1:${port}`);
      let path = join(root, decodeURIComponent(url.pathname));
      if (!path.startsWith(root)) { res.writeHead(403); res.end(); return; }
      if (!existsSync(path) || !statSync(path).isFile()) { res.writeHead(404); res.end('not found'); return; }
      const ext = path.slice(path.lastIndexOf('.'));
      res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream', 'Cache-Control': 'no-store' });
      createReadStream(path).pipe(res);
    });
    server.listen(port, '127.0.0.1', () => resolve({ server, port }));
  });
}

function runChrome(args, outPath, timeoutMs = 20000) {
  return new Promise((resolve, reject) => {
    const p = spawn('google-chrome', args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let err = '';
    let settled = false;
    const finish = (ok, msg) => {
      if (settled) return;
      settled = true;
      clearTimeout(t);
      clearInterval(poll);
      try { p.kill('SIGKILL'); } catch {}
      if (ok) resolve();
      else reject(new Error(msg));
    };
    const t = setTimeout(() => {
      // Chrome often hangs after writing --screenshot; accept file if present.
      if (existsSync(outPath) && statSync(outPath).size > 1000) finish(true);
      else finish(false, `timeout after ${timeoutMs}ms: ${err.slice(-300)}`);
    }, timeoutMs);
    const poll = setInterval(() => {
      if (existsSync(outPath) && statSync(outPath).size > 1000) {
        // Give compositor a brief moment, then succeed.
        setTimeout(() => finish(true), 800);
      }
    }, 400);
    p.stderr.on('data', (d) => { err += d.toString(); });
    p.on('close', (code) => {
      if (existsSync(outPath) && statSync(outPath).size > 1000) finish(true);
      else finish(false, `exit ${code}: ${err.slice(-400)}`);
    });
  });
}

async function chromeShot({ url, out, width, height }) {
  const userData = `/tmp/chrome-g0-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  mkdirSync(userData, { recursive: true });
  if (existsSync(out)) {
    try { writeFileSync(out, ''); } catch {}
  }
  const args = [
    '--headless=new',
    '--disable-gpu',
    '--no-sandbox',
    '--disable-dev-shm-usage',
    '--hide-scrollbars',
    '--force-device-scale-factor=1',
    `--user-data-dir=${userData}`,
    `--window-size=${width},${height}`,
    '--default-background-color=0b0f17',
    `--screenshot=${out}`,
    '--virtual-time-budget=4000',
    '--run-all-compositor-stages-before-draw',
    url,
  ];
  await runChrome(args, out, 18000);
  if (!existsSync(out) || statSync(out).size < 1000) throw new Error('screenshot missing');
  copyFileSync(out, join(artifactDir, out.split('/').pop()));
}

const shots = [
  { name: 'home-desktop-en', page: 'home.html?locale=en', width: 1440, height: 900 },
  { name: 'home-desktop-fa', page: 'home.html?locale=fa', width: 1440, height: 900 },
  { name: 'home-mobile-en', page: 'home.html?locale=en', width: 390, height: 844 },
  { name: 'home-mobile-fa', page: 'home.html?locale=fa', width: 390, height: 844 },
  { name: 'home-mobile-ps', page: 'home.html?locale=ps', width: 390, height: 844 },
  { name: 'detail-desktop-en', page: 'detail.html?locale=en', width: 1440, height: 900 },
  { name: 'detail-desktop-fa', page: 'detail.html?locale=fa', width: 1440, height: 900 },
  { name: 'detail-mobile-en', page: 'detail.html?locale=en', width: 390, height: 844 },
  { name: 'detail-mobile-fa', page: 'detail.html?locale=fa', width: 390, height: 844 },
  { name: 'detail-mobile-ps', page: 'detail.html?locale=ps', width: 390, height: 844 },
  { name: 'home-desktop-1920-en', page: 'home.html?locale=en', width: 1920, height: 1080 },
];

const { server, port } = await startServer(__dirname);
const base = `http://127.0.0.1:${port}`;
console.log('Serving on', base);

const results = [];
for (const s of shots) {
  const out = join(outDir, `${s.name}.png`);
  process.stdout.write(`Capture ${s.name}… `);
  try {
    await chromeShot({ url: `${base}/${s.page}`, out, width: s.width, height: s.height });
    console.log('ok');
    results.push({ ...s, out, ok: true });
  } catch (e) {
    console.log('FAIL', e.message);
    results.push({ ...s, ok: false, error: e.message });
  }
}

writeFileSync(join(outDir, 'manifest.json'), JSON.stringify({ capturedAt: new Date().toISOString(), results }, null, 2));
copyFileSync(join(outDir, 'manifest.json'), join(artifactDir, 'manifest.json'));
server.close();
process.exit(results.some((r) => !r.ok) ? 1 : 0);
