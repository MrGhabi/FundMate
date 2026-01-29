"""
FundMate web application package.

Developer Notes (migrated from docs/src/webapp/__init__.py.md):
- Package entrypoint that exposes the Flask `app` for `python -m src.webapp.app` and WSGI servers.
"""

from .app import app

__all__ = ["app"]
