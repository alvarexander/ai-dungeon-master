/**
 * Tests for reading the cross-site request forgery token from the cookie.
 *
 * Small, but this is the function whose silent failure produces the single
 * most confusing symptom in the whole application: every save returning 403
 * with no clue why.
 */

import { describe, expect, it, afterEach } from 'vitest';

import { isXsrfFailure, readCookie } from './xsrf.interceptor';

/** Remove a cookie so tests do not leak into each other. */
function clearCookie(name: string): void {
    document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
}

describe('readCookie', () => {
    afterEach(() => {
        clearCookie('XSRF-TOKEN');
        clearCookie('OTHER');
    });

    it('finds a cookie by name', () => {
        document.cookie = 'XSRF-TOKEN=abc123; path=/';
        expect(readCookie('XSRF-TOKEN')).toBe('abc123');
    });

    it('returns null when the cookie is absent', () => {
        expect(readCookie('XSRF-TOKEN')).toBeNull();
    });

    it('does not confuse one cookie for another with a similar name', () => {
        document.cookie = 'OTHER=wrong; path=/';
        expect(readCookie('XSRF-TOKEN')).toBeNull();
    });

    it('picks the right cookie when several are set', () => {
        document.cookie = 'OTHER=wrong; path=/';
        document.cookie = 'XSRF-TOKEN=right; path=/';
        expect(readCookie('XSRF-TOKEN')).toBe('right');
    });

    it('decodes an encoded value', () => {
        document.cookie = `XSRF-TOKEN=${encodeURIComponent('a+b/c=')}; path=/`;
        expect(readCookie('XSRF-TOKEN')).toBe('a+b/c=');
    });
});

describe('isXsrfFailure', () => {
    it("recognises the backend's token failure", () => {
        expect(isXsrfFailure({ failure: { code: 'xsrf_failed', status: 403 } })).toBe(true);
    });

    it('recognises any 403, since that is what a missing token produces', () => {
        expect(isXsrfFailure({ failure: { code: 'something_else', status: 403 } })).toBe(true);
    });

    it('does not retry ordinary failures', () => {
        // Retrying these would double the load for no benefit, and retrying a
        // rate-limit failure would actively make it worse.
        expect(isXsrfFailure({ failure: { code: 'rate_limited', status: 429 } })).toBe(false);
        expect(isXsrfFailure({ failure: { code: 'not_found', status: 404 } })).toBe(false);
        expect(isXsrfFailure({ failure: { code: 'upstream_ai_error', status: 502 } })).toBe(false);
    });

    it('does not retry something that is not our error shape', () => {
        expect(isXsrfFailure(new Error('boom'))).toBe(false);
        expect(isXsrfFailure(null)).toBe(false);
    });
});
