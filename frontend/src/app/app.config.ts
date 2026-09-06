/**
 * How the application is wired together.
 *
 * Angular calls this "providers": the list of services and behaviours
 * available everywhere. The order of the HTTP interceptors below matters and
 * is explained where they are listed.
 */

import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors, withXsrfConfiguration } from '@angular/common/http';
import { provideRouter, withComponentInputBinding, withInMemoryScrolling } from '@angular/router';

import { APP_CONFIG, AppConfig } from './core/app-config';
import { authInterceptor } from './core/http/auth.interceptor';
import { credentialsInterceptor } from './core/http/credentials.interceptor';
import { errorInterceptor } from './core/http/error.interceptor';
import { xsrfInterceptor } from './core/http/xsrf.interceptor';
import { routes } from './app.routes';

/**
 * Build the application's provider list.
 *
 * @param config The runtime configuration, already fetched from
 *   `config.json` before the application started.
 * @returns The configuration Angular needs to bootstrap.
 */
export function buildAppConfig(config: AppConfig): ApplicationConfig {
    return {
        providers: [
            // Reports uncaught errors rather than letting them vanish into the
            // console unnoticed.
            provideBrowserGlobalErrorListeners(),

            // Makes the runtime configuration injectable anywhere.
            { provide: APP_CONFIG, useValue: config },

            provideRouter(
                routes,
                // Lets a route parameter arrive as a component input, so components do
                // not have to subscribe to the router to read the id in their URL.
                withComponentInputBinding(),
                // Return to the top on navigation, and honour anchor links. Without
                // this, moving from a long page to a short one leaves the reader
                // scrolled to the middle of the new page, which feels broken.
                withInMemoryScrolling({
                    scrollPositionRestoration: 'top',
                    anchorScrolling: 'enabled'
                })
            ),

            provideHttpClient(
                // Angular's own cross-site request forgery support. Enabled because
                // the brief asks for it and because it covers same-origin requests
                // correctly. It is NOT sufficient on its own here: it deliberately
                // skips absolute URLs, and every one of our requests is absolute
                // because the API is on a different origin. `xsrfInterceptor` below
                // fills that gap. Both are configured with the same names so they can
                // never disagree.
                withXsrfConfiguration({
                    cookieName: 'XSRF-TOKEN',
                    headerName: 'X-XSRF-TOKEN'
                }),

                // Interceptors run in the order listed on the way out, and in reverse
                // on the way back.
                //
                //   credentials — must run first, so the browser is told to include
                //                 cookies before anything else looks at the request.
                //   xsrf        — reads that cookie and echoes it in a header.
                //   auth        — attaches the session token.
                //   error       — outermost on the way back, so it sees every failure
                //                 from the ones above and normalises all of them.
                withInterceptors([credentialsInterceptor, xsrfInterceptor, authInterceptor, errorInterceptor])
            )
        ]
    };
}
