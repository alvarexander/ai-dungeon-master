"""AI Dungeon Master backend service.

This package contains the Python service that sits between the Angular
frontend and Google Gemini. It never sends the Gemini API key to the browser,
never writes personal data in plaintext, and never logs a field that has not
been explicitly declared safe to log.
"""

__version__ = "0.1.0"
