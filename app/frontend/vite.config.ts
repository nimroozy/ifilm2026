import { defineConfig, type Plugin, type ResolvedConfig } from 'vite';
import react from '@vitejs/plugin-react-swc';
import fs from 'node:fs';
import path from 'path';
import { viteSourceLocator } from '@metagptx/vite-plugin-source-locator';
import { atoms } from '@metagptx/web-sdk/plugins';
import { vitePrerenderPlugin } from 'vite-prerender-plugin';
import Sitemap from 'vite-plugin-sitemap';
import { getBlogRoutes } from './prerender/blog-routes.js';
import { getSitemapLastmod } from './prerender/blog-sitemap.js';

function escapeHtmlAttr(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

process.env.VITE_APP_TITLE ??= process.env.OVERVIEW_TITLE ?? 'iFilm Admin';
process.env.VITE_APP_DESCRIPTION ??=
  process.env.OVERVIEW_DESCRIPTION ?? 'iFilm media and catalog administration';
process.env.VITE_APP_TITLE = escapeHtmlAttr(process.env.VITE_APP_TITLE);
process.env.VITE_APP_DESCRIPTION = escapeHtmlAttr(process.env.VITE_APP_DESCRIPTION);
process.env.VITE_APP_LOGO_URL ??= process.env.OVERVIEW_LOGO_URL ?? '/favicon.svg';

function ensureBuildOutDir(): Plugin {
  let outDir = path.resolve(__dirname, 'dist');

  return {
    name: 'ensure-build-out-dir',
    configResolved(config: ResolvedConfig) {
      outDir = path.resolve(config.root, config.build.outDir);
    },
    writeBundle() {
      fs.mkdirSync(outDir, { recursive: true });
    },
  };
}

// https://vitejs.dev/config/
export default defineConfig(({ command }) => {
  const blogPrerenderRoutes = command === 'build' ? getBlogRoutes() : [];

  return {
    plugins: [
      viteSourceLocator({
        prefix: 'mgx', // Prefix used to identify source locations; do not change.
      }),
      react(),
      atoms(),
      ensureBuildOutDir(),
      Sitemap({
        hostname: 'https://ifilm.af',
        lastmod: getSitemapLastmod(),
        readable: true,
        generateRobotsTxt: true,
      }),
      ...(blogPrerenderRoutes.length > 0
        ? vitePrerenderPlugin({
            renderTarget: '#root',
            prerenderScript: path.resolve(__dirname, 'prerender/blog.js'),
            additionalPrerenderRoutes: blogPrerenderRoutes,
          })
        : []),
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      host: '0.0.0.0', // Listen on all network interfaces.
      port: parseInt(process.env.VITE_PORT || '3000'),
      proxy: {
        '/api': {
          target: `http://localhost:${process.env.BACKEND_PORT || '8000'}`,
          changeOrigin: true,
        },
      },
      watch: { usePolling: true, interval: 600 },
      // Looser CSP for Vite HMR only. Production CSP is enforced by the API
      // SecurityHeadersMiddleware (authoritative) when serving FRONTEND_DIST.
      headers: {
        'Content-Security-Policy':
          "default-src 'self'; script-src 'self' 'unsafe-eval'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data: blob: https:; font-src 'self' data: https://fonts.gstatic.com; connect-src 'self' blob: ws: wss: http://127.0.0.1:8000 http://localhost:8000 http://127.0.0.1:3000 http://localhost:3000; media-src 'self' blob:; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self';",
      },
    },
    preview: {
      host: '127.0.0.1',
      port: 4173,
      proxy: {
        '/api': {
          target: `http://localhost:${process.env.BACKEND_PORT || '8000'}`,
          changeOrigin: true,
        },
      },
      // Mirrors backend production CSP for preview-only hosting. Prefer serving
      // dist via FRONTEND_DIST on the API so one middleware owns the header.
      headers: {
        'Content-Security-Policy':
          "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data: blob: https:; font-src 'self' data: https://fonts.gstatic.com; connect-src 'self' blob:; media-src 'self' blob:; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self';",
        'X-Content-Type-Options': 'nosniff',
        'Referrer-Policy': 'no-referrer',
        'X-Frame-Options': 'DENY',
      },
    },
    build: {
      rollupOptions: {
        output: {
          /**
           * Keep only framework vendors forced. Do NOT force Radix / lucide /
           * react-hook-form into shared chunks — that made Vite modulepreload
           * ~1.1MB of admin+form UI on the customer home entry.
           */
          manualChunks(id) {
            if (!id.includes('node_modules')) return undefined;
            if (
              id.includes('node_modules/react-dom') ||
              id.includes('node_modules/react/') ||
              id.includes('node_modules\\react-dom') ||
              id.includes('node_modules\\react\\')
            ) {
              return 'react-vendor';
            }
            if (id.includes('react-router')) return 'router-vendor';
            if (id.includes('@tanstack/react-query')) return 'query-vendor';
            if (id.includes('node_modules/axios') || id.includes('node_modules\\axios')) {
              return 'http-vendor';
            }
            return undefined;
          },
        },
      },
      chunkSizeWarningLimit: 1000,
    },
  };
});
