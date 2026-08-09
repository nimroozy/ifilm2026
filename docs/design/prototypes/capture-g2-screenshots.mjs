#!/usr/bin/env node
/** Capture G2 detail prototypes (movie + series) for plan review. */
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync, copyFileSync, existsSync, createReadStream, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import http from 'node:http';

const __dirname = dirname(fileURLToPath(import.meta.url));
const outDir = join(__dirname, '..', 'screenshots', 'g2');
const artifactDir = '/opt/cursor/artifacts/customer-ui-v2-g2';
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

function startServer(root, port = 8766) {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      const url = new URL(req.url, `http://127.0.0.1:${port}`);
      let path = join(root, decodeURIComponent(url.pathname === '/' ? '/detail.html' : url.pathname));
      if (!path.startsWith(root)) { res.writeHead(403); res.end(); return; }
      if (!existsSync(path) || !statSync(path).isFile()) { res.writeHead(404); res.end('not found'); return; }
      const ext = path.slice(path.lastIndexOf('.'));
      res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream', 'Cache-Control': 'no-store' });
      createReadStream(path).pipe(res);
    });
    server.listen(port, '127.0.0.1', () => resolve({ server, port }));
  });
}

function runChrome(args, outPath, timeoutMs = 25000) {
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
      if (existsSync(outPath) && statSync(outPath).size > 1000) finish(true);
      else finish(false, `timeout: ${err.slice(-300)}`);
    }, timeoutMs);
    const poll = setInterval(() => {
      if (existsSync(outPath) && statSync(outPath).size > 1000) setTimeout(() => finish(true), 800);
    }, 400);
    p.stderr.on('data', (d) => { err += d.toString(); });
    p.on('close', (code) => {
      if (existsSync(outPath) && statSync(outPath).size > 1000) finish(true);
      else finish(false, `exit ${code}: ${err.slice(-400)}`);
    });
  });
}

async function chromeShot({ url, out, width, height }) {
  const userData = `/tmp/chrome-g2-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  mkdirSync(userData, { recursive: true });
  if (existsSync(out)) try { writeFileSync(out, ''); } catch {}
  const args = [
    '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
    `--user-data-dir=${userData}`,
    `--window-size=${width},${height}`,
    `--screenshot=${out}`,
    url,
  ];
  await runChrome(args, out);
}

const shots = [
  { name: 'movie-desktop-en.png', path: '/detail.html?locale=en', w: 1440, h: 900 },
  { name: 'movie-desktop-fa.png', path: '/detail.html?locale=fa', w: 1440, h: 900 },
  { name: 'movie-mobile-en.png', path: '/detail.html?locale=en', w: 390, h: 844 },
  { name: 'series-desktop-en.png', path: '/series-detail.html?locale=en', w: 1440, h: 900 },
  { name: 'series-desktop-fa.png', path: '/series-detail.html?locale=fa', w: 1440, h: 900 },
  { name: 'series-mobile-en.png', path: '/series-detail.html?locale=en', w: 390, h: 844 },
  { name: 'series-mobile-fa.png', path: '/series-detail.html?locale=fa', w: 390, h: 844 },
];

const { server, port } = await startServer(__dirname);
try {
  for (const s of shots) {
    const out = join(outDir, s.name);
    const url = `http://127.0.0.1:${port}${s.path}`;
    console.log('capture', s.name);
    await chromeShot({ url, out, width: s.w, height: s.h });
    copyFileSync(out, join(artifactDir, s.name));
    console.log(' ok', statSync(out).size);
  }
} finally {
  server.close();
}
console.log('done', outDir);
