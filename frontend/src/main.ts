/**
 * The application's entry point: the first code that runs in the browser.
 *
 * WHY CONFIGURATION IS FETCHED BEFORE ANYTHING ELSE
 *
 * The backend's address lives in `config.json` beside the application rather
 * than being compiled in, so that a deployed build can be pointed at a
 * different backend by editing one file on the server. See
 * `app/core/app-config.ts` for the full reasoning.
 *
 * That address is fetched here, before Angular starts. Doing it first means
 * every component can treat the configuration as a plain value that is simply
 * there, rather than something that might not have arrived yet.
 */

import { bootstrapApplication } from '@angular/platform-browser';

import { App } from './app/app';
import { buildAppConfig } from './app/app.config';
import { loadAppConfig } from './app/core/app-config';

/**
 * Show a plain HTML message when the application cannot start at all.
 *
 * At this point Angular is not running, so there are no components and no
 * styling to rely on — this has to be written straight into the page. It
 * exists because the alternative is a blank white screen, which tells the
 * reader nothing about what went wrong or how to fix it.
 *
 * @param error Whatever prevented startup.
 */
function showStartupFailure(error: unknown): void {
    const message = error instanceof Error ? error.message : String(error);
    document.body.innerHTML = `
    <div style="font-family: system-ui, sans-serif; max-width: 640px; margin: 15vh auto;
                padding: 32px; background: #1a1d26; color: #e8ecf3; border-radius: 16px;
                border: 1px solid #3a4152; line-height: 1.6;">
      <h1 style="margin-top: 0; font-size: 1.4rem; color: #f0c164;">
        The application could not start
      </h1>
      <p>${escapeHtml(message)}</p>
      <p style="color: #9aa4b6; font-size: 0.9rem;">
        The most likely causes are that <code>public/config.json</code> is missing, or that
        the backend is not running. See <code>RUNNING.md</code> in the project folder.
      </p>
    </div>`;
}

/**
 * Escape text so it can be safely written into the page.
 *
 * Even an error message must be escaped before being inserted as HTML. Without
 * this, a message containing angle brackets would be interpreted as markup —
 * which is the shape of a cross-site scripting flaw, and worth getting right
 * even in an error path nobody expects to hit.
 *
 * @param value The text to escape.
 * @returns The text with HTML-significant characters replaced.
 */
function escapeHtml(value: string): string {
    const element = document.createElement('div');
    element.textContent = value;
    return element.innerHTML;
}

loadAppConfig()
    .then((config) => bootstrapApplication(App, buildAppConfig(config)))
    .catch((error) => {
        console.error('[startup]', error);
        showStartupFailure(error);
    });
