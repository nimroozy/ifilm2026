#!/usr/bin/env node
/**
 * Customer initial JS budget for homepage entry (PR #58).
 *
 * Measures bytes referenced from dist/index.html (modulepreload + entry scripts),
 * excluding admin/player/route chunks that are not part of the customer home shell.
 *
 * Before (07024dd): ~1,108,574 bytes (~1083 KB) initial JS
 * Budget: fail if customer initial JS exceeds the threshold below.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const distDir = path.resolve(__dirname, '../dist');
const htmlPath = path.join(distDir, 'index.html');

/** Soft stretch target after Fast3G hardening; warn above this. */
const WARN_BYTES = 720 * 1024;
/** Hard CI fail — material cut vs ~1083 KB baseline (~1.1MB). */
const FAIL_BYTES = 850 * 1024;
const BASELINE_BEFORE_BYTES = 1108574;

if (!fs.existsSync(htmlPath)) {
  console.error('check-customer-bundle-budget: dist/index.html missing. Run pnpm build first.');
  process.exit(1);
}

const html = fs.readFileSync(htmlPath, 'utf8');
const refs = [...html.matchAll(/(?:src|href)="(\/?assets\/[^"]+\.(?:js|css))"/g)].map((m) =>
  m[1].replace(/^\//, '')
);

const assetsDir = path.join(distDir, 'assets');
let initialJs = 0;
let initialCss = 0;
const rows = [];

for (const rel of refs) {
  const file = path.basename(rel);
  const full = path.join(assetsDir, file);
  if (!fs.existsSync(full)) continue;
  const size = fs.statSync(full).size;
  if (file.endsWith('.js')) {
    initialJs += size;
    rows.push({ kind: 'js', file, size });
  } else {
    initialCss += size;
    rows.push({ kind: 'css', file, size });
  }
}

rows.sort((a, b) => b.size - a.size);

const report = {
  baseline_before_bytes: BASELINE_BEFORE_BYTES,
  initial_js_bytes: initialJs,
  initial_css_bytes: initialCss,
  warn_budget_bytes: WARN_BYTES,
  fail_budget_bytes: FAIL_BYTES,
  files: rows,
  reduced_vs_baseline_bytes: BASELINE_BEFORE_BYTES - initialJs,
  reduced_vs_baseline_pct: Number(
    (((BASELINE_BEFORE_BYTES - initialJs) / BASELINE_BEFORE_BYTES) * 100).toFixed(1)
  ),
};

const outDir = process.env.PERF_ARTIFACT_DIR || '/opt/cursor/artifacts/perf-customer-browsing-v1';
try {
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, 'bundle-budget.json'), JSON.stringify(report, null, 2));
} catch {
  // Artifacts dir may be unavailable in some CI sandboxes; stdout is enough.
}

console.log('Customer initial bundle budget');
console.log(`  Before (07024dd): ${(BASELINE_BEFORE_BYTES / 1024).toFixed(1)} KB`);
console.log(`  Current initial JS: ${(initialJs / 1024).toFixed(1)} KB (${initialJs} bytes)`);
console.log(`  Current initial CSS: ${(initialCss / 1024).toFixed(1)} KB`);
console.log(`  Delta vs before: ${report.reduced_vs_baseline_pct}% (${report.reduced_vs_baseline_bytes} bytes)`);
console.log(`  Warn budget: ${(WARN_BYTES / 1024).toFixed(0)} KB | Fail budget: ${(FAIL_BYTES / 1024).toFixed(0)} KB`);
console.log('  Entry files:');
for (const row of rows) {
  console.log(`    ${row.kind.toUpperCase()} ${(row.size / 1024).toFixed(1)} KB  ${row.file}`);
}

if (initialJs > FAIL_BYTES) {
  console.error(
    `\nFAIL: customer initial JS ${(initialJs / 1024).toFixed(1)} KB exceeds fail budget ${(FAIL_BYTES / 1024).toFixed(0)} KB`
  );
  process.exit(1);
}
if (initialJs > WARN_BYTES) {
  console.warn(
    `\nWARN: customer initial JS ${(initialJs / 1024).toFixed(1)} KB exceeds warn budget ${(WARN_BYTES / 1024).toFixed(0)} KB`
  );
}
console.log('\nOK: within fail budget');
