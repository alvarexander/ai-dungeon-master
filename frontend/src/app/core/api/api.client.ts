/**
 * A thin wrapper around Angular's HTTP client that knows where the backend is.
 *
 * WHY THIS EXISTS RATHER THAN CALLING HttpClient DIRECTLY
 *
 * Every feature would otherwise have to build its own full URLs by combining
 * the configured base address with a path. That is repeated everywhere, and
 * the first time somebody writes a path without the base address they get a
 * request to the Angular development server instead of the backend, which
 * fails with a confusing 404 from the wrong program.
 *
 * Centralising it also means there is exactly one place where the API address
 * is read, which makes it easy to prove that no `localhost` is written into
 * any source file.
 */

import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { APP_CONFIG } from '../app-config';

/** Query string values, before they are converted to text. */
export type QueryParams = Record<string, string | number | boolean | undefined>;

@Injectable({ providedIn: 'root' })
export class ApiClient {
  private readonly http = inject(HttpClient);
  private readonly config = inject(APP_CONFIG);

  /**
   * Build the full address of an endpoint.
   *
   * @param path The path, starting with a slash, e.g. `/api/v1/campaigns`.
   * @returns The complete URL.
   */
  url(path: string): string {
    return `${this.config.apiBaseUrl}${path}`;
  }

  /**
   * Convert a plain object into query parameters, dropping empty values.
   *
   * @param params The values to include.
   * @returns Angular's parameter object.
   */
  private toParams(params?: QueryParams): HttpParams {
    let httpParams = new HttpParams();
    for (const [key, value] of Object.entries(params ?? {})) {
      if (value !== undefined && value !== null && value !== '') {
        httpParams = httpParams.set(key, String(value));
      }
    }
    return httpParams;
  }

  /**
   * Send a GET request.
   *
   * A reminder enforced by review rather than by code: **never put personal
   * data in these parameters.** Query strings are recorded in server access
   * logs, browser history and proxy logs, all of which sit outside the
   * encryption boundary. Identifiers and page numbers only.
   *
   * @param path The endpoint path.
   * @param params Optional query parameters.
   * @returns The parsed response.
   */
  get<T>(path: string, params?: QueryParams): Observable<T> {
    return this.http.get<T>(this.url(path), { params: this.toParams(params) });
  }

  /**
   * Send a POST request.
   *
   * @param path The endpoint path.
   * @param body The request body, sent as JSON.
   * @returns The parsed response.
   */
  post<T>(path: string, body: unknown): Observable<T> {
    return this.http.post<T>(this.url(path), body);
  }

  /**
   * Send a PATCH request, for partial updates.
   *
   * @param path The endpoint path.
   * @param body The fields to change.
   * @returns The parsed response.
   */
  patch<T>(path: string, body: unknown): Observable<T> {
    return this.http.patch<T>(this.url(path), body);
  }

  /**
   * Send a DELETE request.
   *
   * @param path The endpoint path.
   * @returns The parsed response.
   */
  delete<T>(path: string): Observable<T> {
    return this.http.delete<T>(this.url(path));
  }

  /**
   * Upload a file.
   *
   * Used for voice recordings. The body is `FormData` rather than JSON, and
   * the `Content-Type` header is deliberately not set — the browser must set
   * it itself, because it has to include a generated boundary marker that
   * separates the parts of the upload. Setting it by hand produces an upload
   * the server cannot parse, which is a classic afternoon lost.
   *
   * @param path The endpoint path.
   * @param formData The multipart body.
   * @returns The parsed response.
   */
  upload<T>(path: string, formData: FormData): Observable<T> {
    return this.http.post<T>(this.url(path), formData);
  }
}
