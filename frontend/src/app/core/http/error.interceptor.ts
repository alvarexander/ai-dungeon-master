/**
 * Turns backend errors into a consistent, displayable shape.
 *
 * WHY ERRORS GET THEIR OWN LAYER
 *
 * Without this, every component would have to understand HTTP status codes and
 * the backend's error format, and each would present failures slightly
 * differently. Worse, the piece that actually matters for support — the
 * correlation identifier — would be discarded, because it arrives in a header
 * that nobody thought to read.
 *
 * THE CORRELATION IDENTIFIER
 *
 * Every response from the backend carries `X-Correlation-ID`, a random value
 * identifying that one request. It is stamped on every log line the request
 * produced. When something goes wrong, the interface shows it, and quoting it
 * is enough to find the whole story in the logs.
 *
 * This matters more here than in most applications. The backend cannot look up
 * a user's data to investigate a problem — it is encrypted, and that is the
 * point. The correlation identifier is what replaces that, so it is treated as
 * a first-class part of every failure rather than as debugging trivia.
 */

import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { catchError, throwError } from 'rxjs';

/** A backend failure, reduced to what the interface needs. */
export interface ApiFailure {
    /**
     * A stable machine-readable code such as `rate_limited` or
     * `ai_quota_exhausted`. Branch on this, never on the message text, which may
     * be reworded at any time.
     */
    code: string;

    /** A plain-language explanation, safe to show the user. */
    message: string;

    /** The identifier to quote when reporting the problem. May be empty. */
    correlationId: string;

    /** The HTTP status. 0 means the server could not be reached at all. */
    status: number;

    /** For a rate limit, how many seconds to wait. */
    retryAfterSeconds?: number;
}

/** Distinguishes our failures from any other thrown value. */
export class ApiError extends Error {
    constructor(readonly failure: ApiFailure) {
        super(failure.message);
        this.name = 'ApiError';
    }
}

/**
 * Converts an HTTP failure into an `ApiError`.
 *
 * @param response Whatever the HTTP layer threw.
 * @returns A failure with a message worth showing someone.
 */
function toFailure(response: HttpErrorResponse): ApiFailure {
    const correlationId = response.headers?.get('X-Correlation-ID') ?? '';

    // Status 0 means the request never arrived: the server is not running, the
    // network is down, or CORS blocked it. This is the single most common
    // failure during local development, so it gets a specific message rather
    // than a generic "something went wrong".
    if (response.status === 0) {
        return {
            code: 'network_unreachable',
            message: 'Could not reach the server. Check that the backend is running, then try again.',
            correlationId,
            status: 0
        };
    }

    const body = response.error as { error?: { code?: string; message?: string } } | null;
    const detail = body?.error;

    const retryAfterHeader = response.headers?.get('Retry-After');

    return {
        code: detail?.code ?? 'unknown_error',
        message: detail?.message ?? 'Something went wrong. Please try again.',
        correlationId,
        status: response.status,
        retryAfterSeconds: retryAfterHeader ? Number(retryAfterHeader) : undefined
    };
}

/**
 * Catches every failed request and rethrows it in a consistent shape.
 *
 * @param request The outgoing request.
 * @param next Passes the request on.
 * @returns The response stream, with failures normalised.
 */
export const errorInterceptor: HttpInterceptorFn = (request, next) =>
    next(request).pipe(
        catchError((response: HttpErrorResponse) => throwError(() => new ApiError(toFailure(response))))
    );
