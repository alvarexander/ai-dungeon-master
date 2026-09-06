/**
 * Attaches the session token to requests aimed at our API.
 *
 * PHASE 1 NOTE
 * The token is a placeholder that the backend does not verify — see
 * `SessionStore` for exactly where that line falls. This interceptor is
 * written as though the token were real, so that when Phase 2 replaces the
 * token itself, nothing here changes.
 */

import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';

import { APP_CONFIG } from '../app-config';
import { SessionStore } from '../state/session.store';

/**
 * Adds the `Authorization` header when a token is held.
 *
 * @param request The outgoing request.
 * @param next Passes the request on.
 * @returns The response stream.
 */
export const authInterceptor: HttpInterceptorFn = (request, next) => {
    const config = inject(APP_CONFIG);
    const session = inject(SessionStore);

    // Scoped to our own backend. Sending a session token to any other address
    // would hand a credential to a third party.
    if (!request.url.startsWith(config.apiBaseUrl)) {
        return next(request);
    }

    const token = session.token();
    if (!token) {
        // No token is a valid state in Phase 1: the backend then treats the
        // request as the demo account, which is what lets the interface be
        // explored without signing in.
        return next(request);
    }

    return next(request.clone({ setHeaders: { Authorization: `Bearer ${token}` } }));
};
