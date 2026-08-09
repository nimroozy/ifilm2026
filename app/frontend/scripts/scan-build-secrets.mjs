#!/usr/bin/env node
/**
 * Scan frontend build output for leaked secrets (Train T0).
 *
 * Allowed public config uses the Vite allowlist (VITE_* public keys / VITE_PUBLIC_*).
 * Forbidden: JWT, playback HMAC, DB/Redis passwords, TMDB tokens, storage keys.
 *
 * Usage: node scripts/scan-build-secrets.mjs [distDir]
 */
import { readdirSync, readFileSync, statSync, existsSync } from 'node:fs';
import { join, relative } from 'node:path';

const distDir = process.argv[2] || join(process.cwd(), 'dist');

const FORBIDDEN = [
  { name: 'JWT_SECRET assignment', re: /JWT_SECRET\s*[:=]\s*['"][^'"]+['"]/i },
  { name: 'PLAYBACK_TOKEN_SECRET', re: /PLAYBACK_TOKEN_SECRET\s*[:=]/i },
  { name: 'TMDB API key assignment', re: /TMDB[_A-Z]*API[_A-Z]*KEY\s*[:=]\s*['"][^'"]+['"]/i },
  { name: 'Postgres password', re: /POSTGRES_PASSWORD\s*[:=]/i },
  { name: 'Redis password', re: /REDIS_PASSWORD\s*[:=]/i },
  { name: 'AWS secret key', re: /AWS_SECRET_ACCESS_KEY\s*[:=]/i },
  { name: 'Private key block', re: /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/ },
  { name: 'Bearer token literal', re: /Bearer\s+[A-Za-z0-9\-_]{20,}\.[A-Za-z0-9\-_]{10,}/ },
];

// Build artifacts may mention allowlisted VITE_ keys as string names — that is OK.
const ALLOWED_VITE_PREFIXES = ['VITE_PUBLIC_', 'VITE_API_', 'VITE_DATA_', 'VITE_APP_', 'VITE_SITE_', 'VITE_TWITTER_', 'VITE_PORT'];

function walk(dir, out = []) {
  if (!existsSync(dir)) return out;
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) walk(p, out);
    else if (/\.(js|mjs|cjs|css|html|map|json|txt)$/i.test(name)) out.push(p);
  }
  return out;
}

if (!existsSync(distDir)) {
  console.error(`scan-build-secrets: dist not found at ${distDir}`);
  process.exit(2);
}

const files = walk(distDir);
const hits = [];

for (const file of files) {
  let text;
  try {
    text = readFileSync(file, 'utf8');
  } catch {
    continue;
  }
  // Flag any VITE_ env that looks secret-shaped (not on public allowlist prefixes).
  const viteKeys = text.match(/VITE_[A-Z0-9_]+/g) || [];
  for (const key of new Set(viteKeys)) {
    const allowed = ALLOWED_VITE_PREFIXES.some((p) => key.startsWith(p));
    const secretShaped = /SECRET|PASSWORD|TOKEN|API_KEY|PRIVATE|CREDENTIAL/i.test(key);
    if (secretShaped && !allowed) {
      hits.push({ file, name: `forbidden Vite key ${key}`, sample: key });
    }
  }
  for (const rule of FORBIDDEN) {
    const m = text.match(rule.re);
    if (m) {
      hits.push({
        file,
        name: rule.name,
        sample: m[0].slice(0, 80),
      });
    }
  }
}

if (hits.length) {
  console.error('scan-build-secrets: FAILED — potential secrets in frontend build output:');
  for (const h of hits) {
    console.error(`  - ${relative(process.cwd(), h.file)}: ${h.name} :: ${h.sample}`);
  }
  process.exit(1);
}

console.log(`scan-build-secrets: OK (${files.length} files scanned under ${distDir})`);
