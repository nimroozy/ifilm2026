import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => {
  vi.resetModules();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('getAPIBaseURL', () => {
  it('returns the default API base URL when runtime config is unavailable', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        headers: { get: () => null },
      })
    );

    const { loadRuntimeConfig, getAPIBaseURL } = await import('./config');
    await loadRuntimeConfig();

    expect(getAPIBaseURL()).toBe('http://127.0.0.1:8000');
  });

  it('returns an empty string when API_BASE_URL is "/"', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({ API_BASE_URL: '/' }),
      })
    );

    const { loadRuntimeConfig, getAPIBaseURL } = await import('./config');
    await loadRuntimeConfig();

    expect(getAPIBaseURL()).toBe('');
  });
});
