/**
 * Runtime configuration, fetched when the page loads.
 *
 * WHY THIS IS NOT AN ANGULAR `environment.ts` FILE
 *
 * Angular's usual approach bakes configuration into the JavaScript at build
 * time: you build one bundle for development and a different one for
 * production, each with the backend address compiled in.
 *
 * That is a poor fit for how this application is deployed. The Angular app is
 * uploaded to Hostinger as plain files. If the backend address were compiled
 * in, then changing it — moving the backend, adding a staging environment,
 * correcting a typo in a domain — would mean rebuilding the whole application
 * and re-uploading every file.
 *
 * Instead the address lives in `public/config.json`, a small file sitting
 * beside the application, which the app fetches before it starts. Changing
 * where a deployed build points is then a matter of editing one file on the
 * server. Build once, configure anywhere.
 *
 * This also satisfies a hard rule of this project: no `localhost` is written
 * into any source file. The value in `config.json` is configuration, in the
 * one place configuration belongs.
 */

import { InjectionToken } from '@angular/core';

/** The shape of `public/config.json`. */
export interface AppConfig {
  /**
   * Where the backend lives, with no trailing slash.
   * For example `http://localhost:8000` locally, or
   * `https://api.yourdomain.com` in production.
   */
  apiBaseUrl: string;

  /**
   * Which environment this is. The interface uses it to decide whether to show
   * the "demo mode" banner, so a stubbed screen is never mistaken for a real
   * one.
   */
  environment: 'local' | 'staging' | 'production';
}

/**
 * How the configuration is handed to the rest of the application.
 *
 * An injection token is Angular's way of naming a value so that any component
 * can ask for it without knowing where it came from. That indirection is what
 * lets a test supply a different configuration without touching a network.
 */
export const APP_CONFIG = new InjectionToken<AppConfig>('APP_CONFIG');

/**
 * Fetches `config.json` before the application starts.
 *
 * Called from `main.ts` ahead of bootstrapping, so that by the time any
 * component exists the configuration is already known. Components can then
 * treat it as a plain value rather than something that might not have arrived
 * yet.
 *
 * @returns The parsed configuration.
 * @throws If the file is missing or malformed. This is deliberate: an
 *   application that started with no backend address would fail later with a
 *   confusing network error on the first request. Failing immediately, with a
 *   message naming the file, is far easier to act on.
 */
export async function loadAppConfig(): Promise<AppConfig> {
  let response: Response;
  try {
    // A cache-busting query string. Without it, a browser that cached the old
    // configuration would keep talking to the previous backend after a
    // deployment — a genuinely baffling problem to debug.
    response = await fetch(`config.json?v=${Date.now()}`, { cache: 'no-store' });
  } catch (cause) {
    throw new Error(
      'Could not load config.json. The application cannot start without knowing ' +
        'where the backend is. Check that public/config.json exists.',
      { cause },
    );
  }

  if (!response.ok) {
    throw new Error(
      `Could not load config.json (HTTP ${response.status}). This file must be ` +
        'deployed alongside the application.',
    );
  }

  const config = (await response.json()) as Partial<AppConfig>;

  if (!config.apiBaseUrl) {
    throw new Error(
      'config.json does not contain "apiBaseUrl". Set it to the address of the ' +
        'backend, for example "http://localhost:8000".',
    );
  }

  return {
    // A trailing slash here would produce URLs with a doubled slash, which some
    // servers treat as a different path. Removing it once, here, avoids a
    // whole category of confusing 404s.
    apiBaseUrl: config.apiBaseUrl.replace(/\/+$/, ''),
    environment: config.environment ?? 'local',
  };
}
