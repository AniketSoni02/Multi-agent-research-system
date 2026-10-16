"""Vercel entrypoint: Vercel looks for an ASGI `app` in a root-level app.py."""

from backend.main import app  # noqa: F401
