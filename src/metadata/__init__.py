"""
Metadata subpackage for FundMate.

Developer Notes (migrated from docs/src/metadata/__init__.py.md):
- Package entrypoint that re-exports core metadata types for external imports; it contains no business logic.
"""

from .detector import StatementMetadata, StatementMetadataDetector

__all__ = ["StatementMetadata", "StatementMetadataDetector"]
