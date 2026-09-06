"""A Swagger documentation page that works with cross-site request forgery protection.

THE PROBLEM THIS SOLVES
FastAPI generates a browsable documentation page at `/docs` with a "Try it
out" button on every endpoint. It is the fastest way to explore an API.

But this application requires a cross-site request forgery token on every
state-changing request, and the stock documentation page knows nothing about
that. So pressing "Try it out" on any POST produces:

    {"error": {"code": "xsrf_failed", ...}}

Two bad answers were rejected before arriving at this one:

- **Exempt `/docs` from the protection.** This would leave a hole that exists
  in production as well as locally, and the whole point of the protection is
  that it has no exceptions.
- **Have the reader paste the token in by hand.** It works, but it means
  finding the cookie in the browser's developer tools before every single
  request, which makes the documentation page useless in practice.

THE ANSWER
Serve the same Swagger interface with one extra behaviour: a request
interceptor that reads the token from the cookie and attaches the header,
exactly as the real Angular application does. The documentation page becomes a
well-behaved client rather than an exempt one, and the protection stays intact
everywhere.
"""

from __future__ import annotations

from fastapi.responses import HTMLResponse

# Pinned to an exact version rather than "latest". An unpinned CDN reference is
# a standing invitation for someone else's change to alter a page in our
# application without warning.
SWAGGER_VERSION = "5.17.14"

_DOCS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} — API documentation</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@{version}/swagger-ui.css">
  <style>
    body {{ margin: 0; background: #fafafa; }}
    .xsrf-note {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #1f2933; color: #e8eef5; padding: 14px 20px;
      font-size: 14px; line-height: 1.55; border-bottom: 3px solid #b8862b;
    }}
    .xsrf-note strong {{ color: #f0c164; }}
    .xsrf-note code {{
      background: rgba(255,255,255,.12); padding: 1px 6px; border-radius: 4px;
    }}
  </style>
</head>
<body>
  <div class="xsrf-note">
    <strong>Cross-site request forgery protection is active.</strong>
    This page reads the <code>XSRF-TOKEN</code> cookie and attaches it as the
    <code>X-XSRF-TOKEN</code> header on every request, so &ldquo;Try it out&rdquo; works
    normally. If a request is refused with <code>xsrf_failed</code>, reload this page once
    to obtain a fresh token.
  </div>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@{version}/swagger-ui-bundle.js"></script>
  <script>
    window.ui = SwaggerUIBundle({{
      url: '{openapi_url}',
      dom_id: '#swagger-ui',
      presets: [SwaggerUIBundle.presets.apis],
      layout: 'BaseLayout',
      deepLinking: true,
      displayRequestDuration: true,
      tryItOutEnabled: true,
      // This is the whole reason for a custom page. Every outgoing request
      // passes through here first, and picks up the token the same way the
      // Angular application does.
      requestInterceptor: function (request) {{
        var match = document.cookie.match(/(?:^|;\\s*)XSRF-TOKEN=([^;]+)/);
        if (match) {{
          request.headers['X-XSRF-TOKEN'] = decodeURIComponent(match[1]);
        }}
        // Same origin as this page, so the browser sends the cookie itself.
        request.credentials = 'same-origin';
        return request;
      }}
    }});
  </script>
</body>
</html>
"""


def swagger_page(title: str, openapi_url: str) -> HTMLResponse:
    """Build the documentation page.

    Args:
        title: Shown in the browser tab.
        openapi_url: Where the machine-readable API description lives.

    Returns:
        The rendered page.
    """
    return HTMLResponse(
        _DOCS_HTML.format(title=title, version=SWAGGER_VERSION, openapi_url=openapi_url)
    )
