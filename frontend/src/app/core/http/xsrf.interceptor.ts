/**
 * Attaches the cross-site request forgery token to requests aimed at our API.
 *
 * WHY THIS EXISTS WHEN ANGULAR ALREADY HAS XSRF SUPPORT
 *
 * Angular ships cross-site request forgery protection, configured with
 * `withXsrfConfiguration`, and this application enables it. But it has a
 * limitation that is easy to miss and produces a baffling failure:
 *
 * **Angular only attaches the token to relative URLs.** It assumes the API is
 * on the same origin as the page, and deliberately refuses to send the token
 * to an absolute URL — a sensible default, since you would not want your
 * token posted to any third-party address a component happened to call.
 *
 * Our API is on a different origin by design: the Angular app is on Hostinger
 * and the backend is on Fly.io. So every request is absolute, Angular attaches
 * nothing, and every state-changing request is refused by the backend with a
 * 403 that gives no hint why.
 *
 * This interceptor closes that gap. It attaches the token to requests aimed at
 * the configured API base address, and to nothing else.
 *
 * WHAT XSRF IS, BRIEFLY
 *
 * An attack that abuses the fact that browsers attach cookies automatically,
 * whichever site caused the request. A malicious page can silently submit a
 * form to our API, and the browser helpfully includes your session. The
 * defence is a token the server puts in a readable cookie: the real
 * application reads it and echoes it in a header, and the attacker's page
 * cannot, because browsers forbid one site reading another's cookies.
 *
 * THE DEPLOYMENT REQUIREMENT THIS IMPLIES
 *
 * For the frontend to read a cookie the backend set, both must share a parent
 * domain — `app.example.com` and `api.example.com`, with the backend setting
 * `COOKIE_DOMAIN=.example.com`. Locally this is free, because both are
 * `localhost` and cookies ignore port numbers. In production it is a
 * constraint to plan for. See `backend/app/middleware/xsrf.py`.
 */

import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';

import { APP_CONFIG } from '../app-config';

/** The cookie the backend writes the token into. Must match `XSRF_COOKIE_NAME`. */
const XSRF_COOKIE_NAME = 'XSRF-TOKEN';

/** The header the backend expects it echoed in. Must match `XSRF_HEADER_NAME`. */
const XSRF_HEADER_NAME = 'X-XSRF-TOKEN';

/** Methods that only read, and therefore need no token. */
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

/**
 * Reads one cookie from `document.cookie`.
 *
 * There is no browser method for reading a single cookie — `document.cookie`
 * is one long string of `name=value` pairs separated by semicolons, so it has
 * to be parsed by hand.
 *
 * @param name The cookie to look for.
 * @returns The decoded value, or `null` if it is not present. `null` is the
 *   normal state before the first request, and also the symptom of the
 *   cross-domain problem described in this file's header comment.
 */
export function readCookie(name: string): string | null {
  const match = document.cookie
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${name}=`));

  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

/**
 * Adds the token header to state-changing requests sent to our own API.
 *
 * @param request The outgoing request.
 * @param next Passes the request on to the next interceptor.
 * @returns The response stream.
 */
export const xsrfInterceptor: HttpInterceptorFn = (request, next) => {
  const config = inject(APP_CONFIG);

  // Only our own API. Sending the token anywhere else would hand it to a third
  // party, which is the exact thing the token exists to prevent.
  const isOurApi = request.url.startsWith(config.apiBaseUrl);
  if (!isOurApi || SAFE_METHODS.has(request.method.toUpperCase())) {
    return next(request);
  }

  const token = readCookie(XSRF_COOKIE_NAME);
  if (!token) {
    // Deliberately allowed through rather than blocked here. The backend will
    // refuse it with a clear 403, which is more useful than a silent failure
    // in the browser — and this warning names the likely cause.
    console.warn(
      `[xsrf] No ${XSRF_COOKIE_NAME} cookie found, so this ${request.method} request ` +
        'will be refused by the server. If this happens in production, the API and the ' +
        'app are probably not under a shared parent domain — see COOKIE_DOMAIN in the ' +
        "backend's configuration.",
    );
    return next(request);
  }

  return next(request.clone({ setHeaders: { [XSRF_HEADER_NAME]: token } }));
};
