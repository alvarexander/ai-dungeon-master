/**
 * Makes the browser include cookies on requests to our API.
 *
 * WHY THIS IS NECESSARY
 *
 * By default, a browser does **not** send cookies with a request to a
 * different origin. Since our API is on a different origin from the page, that
 * default would mean the cross-site request forgery cookie never travels, and
 * every state-changing request would be refused.
 *
 * Setting `withCredentials` tells the browser to include them anyway. It only
 * works when the server also permits it, which the backend does by setting
 * `allow_credentials=True` in its CORS configuration. Both halves are
 * required; either alone does nothing.
 *
 * WHY THIS IS SCOPED TO OUR OWN API
 *
 * `withCredentials` is applied only to requests aimed at the configured
 * backend. Applying it to every outgoing request would send our cookies to any
 * third-party address the application ever calls.
 */

import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';

import { APP_CONFIG } from '../app-config';

/**
 * Enables cookie sending for requests to our backend.
 *
 * @param request The outgoing request.
 * @param next Passes the request on.
 * @returns The response stream.
 */
export const credentialsInterceptor: HttpInterceptorFn = (request, next) => {
  const config = inject(APP_CONFIG);

  if (!request.url.startsWith(config.apiBaseUrl)) {
    return next(request);
  }

  return next(request.clone({ withCredentials: true }));
};
