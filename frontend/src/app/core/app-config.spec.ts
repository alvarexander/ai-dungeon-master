/**
 * Tests for loading the runtime configuration.
 *
 * The behaviour worth pinning down is the failure path. A missing or malformed
 * `config.json` must stop the application immediately with a message naming
 * the file — not start successfully and then fail confusingly on the first
 * request with a network error nobody can trace back to a config problem.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import { loadAppConfig } from './app-config';

/**
 * Replace `fetch` with a stub for one test.
 *
 * @param response What the stubbed fetch should return.
 */
function stubFetch(response: Partial<Response> & { json?: () => Promise<unknown> }): void {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
}

describe('loadAppConfig', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('reads the backend address', async () => {
    stubFetch({
      ok: true,
      json: async () => ({ apiBaseUrl: 'https://api.example.com', environment: 'production' }),
    });

    const config = await loadAppConfig();

    expect(config.apiBaseUrl).toBe('https://api.example.com');
    expect(config.environment).toBe('production');
  });

  it('strips a trailing slash from the address', async () => {
    // Without this, every URL would contain a doubled slash, which some
    // servers treat as a different path and answer with a puzzling 404.
    stubFetch({ ok: true, json: async () => ({ apiBaseUrl: 'https://api.example.com/' }) });

    const config = await loadAppConfig();

    expect(config.apiBaseUrl).toBe('https://api.example.com');
  });

  it('defaults the environment to local when it is not stated', async () => {
    stubFetch({ ok: true, json: async () => ({ apiBaseUrl: 'https://api.example.com' }) });

    const config = await loadAppConfig();

    expect(config.environment).toBe('local');
  });

  it('refuses to start when the file is missing', async () => {
    stubFetch({ ok: false, status: 404 });

    await expect(loadAppConfig()).rejects.toThrow(/config\.json/);
  });

  it('refuses to start when the backend address is absent', async () => {
    stubFetch({ ok: true, json: async () => ({ environment: 'local' }) });

    await expect(loadAppConfig()).rejects.toThrow(/apiBaseUrl/);
  });

  it('refuses to start when the file cannot be fetched at all', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')));

    await expect(loadAppConfig()).rejects.toThrow(/cannot start/);
  });
});
