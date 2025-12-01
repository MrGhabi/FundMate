#!/usr/bin/env python3
"""Organize statement files into canonical naming based on metadata JSONL."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from shutil import move
from typing import Optional, Dict

from loguru import logger
import hashlib
import re


@dataclass
class MetadataRecord:
    file: Path
    broker_name: Optional[str]
    account_id: Optional[str]
    statement_date: Optional[str]

    @classmethod
    def from_json(cls, data: dict) -> "MetadataRecord":
        return cls(
            file=Path(data["file"]),
            broker_name=data.get("broker_name"),
            account_id=data.get("account_id"),
            statement_date=data.get("statement_date"),
        )

    def canonical_filename(self) -> Optional[str]:
        if not self.broker_name or not self.statement_date:
            return None
        account = self.account_id or "UNKNOWN"
        return f"{self.broker_name}_{self.statement_date}_{account}{self.file.suffix}"


def read_metadata(jsonl_path: Path) -> list[MetadataRecord]:
    records = []
    with jsonl_path.open() as f:
        for line in f:
            data = json.loads(line)
            records.append(MetadataRecord.from_json(data))
    return records


def organize_files(records: list[MetadataRecord], output_dir: Path, dry_run: bool = False):
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_root = Path("data/archives").resolve()
    output_root = output_dir.resolve()
    dedupe_enabled = output_root == archive_root
    hash_cache: Dict[str, Dict[str, Optional[str]]] = {}

    for record in records:
        target_name = record.canonical_filename()
        if not target_name:
            logger.warning(f"Skipping {record.file} due to missing broker/date")
            continue

        target_path = output_dir / target_name

        if dedupe_enabled and record.broker_name:
            broker_hashes = _load_archive_hashes(record.broker_name, archive_root, hash_cache)
            file_hash = _compute_sha256(record.file)
            existing_date = broker_hashes.get(file_hash)
            if existing_date:
                if existing_date == record.statement_date:
                    logger.info(
                        f"Duplicate detected for {record.file} (hash match, date {existing_date}), skipping archive write."
                    )
                    continue
                else:
                    logger.error(
                        "Hash conflict for %s: archive date %s vs detected date %s. Skipping file.",
                        record.file,
                        existing_date,
                        record.statement_date,
                    )
                    continue

        target_path = _resolve_target_path(record.file, target_path)
        if target_path.exists():
            existing_hash = _compute_sha256(target_path)
            new_hash = _compute_sha256(record.file)
            if existing_hash == new_hash:
                logger.info(f"Duplicate content detected, skipping move: {record.file} -> {target_path}")
                continue
            target_path = _resolve_variant_target(record.file, target_path)

        if dry_run:
            logger.info(f"[DRY RUN] {record.file} -> {target_path}")
            continue

        target_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Moving {record.file} -> {target_path}")
        move(str(record.file), target_path)

        if dedupe_enabled and record.broker_name:
            broker_hashes = _load_archive_hashes(record.broker_name, archive_root, hash_cache)
            broker_hashes[_compute_sha256(target_path)] = record.statement_date


def _compute_sha256(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _load_archive_hashes(
    broker: str,
    archive_root: Path,
    cache: Dict[str, Dict[str, Optional[str]]]
) -> Dict[str, Optional[str]]:
    if broker in cache:
        return cache[broker]

    broker_dir = archive_root / broker
    mapping: Dict[str, Optional[str]] = {}

    if broker_dir.exists():
        for file in broker_dir.iterdir():
            if not file.is_file():
                continue
            file_hash = _compute_sha256(file)
            mapping[file_hash] = _extract_date(file.name)

    cache[broker] = mapping
    return mapping


def _extract_date(name: str) -> Optional[str]:
    match = DATE_PATTERN.search(name)
    if match:
        return match.group(1)
    return None


def _resolve_target_path(source: Path, target: Path) -> Path:
    """Handle existing target path collisions by appending a variant suffix."""
    if not target.exists():
        return target
    return _resolve_variant_target(source, target)


def _resolve_variant_target(source: Path, target: Path) -> Path:
    base = target.stem
    ext = target.suffix
    suffix = _derive_suffix_from_name(source.name)
    candidates = []
    if suffix:
        candidates.append(target.with_name(f"{base}_{suffix}{ext}"))
    # Fallback to numbered variants.
    n = 1
    while True:
        name = f"{base}_{suffix or 'v'}{n}{ext}"
        candidate = target.with_name(name)
        candidates.append(candidate)
        n += 1
        # Return the first non-existing candidate.
        for cand in candidates:
            if not cand.exists():
                return cand


def _derive_suffix_from_name(name: str) -> Optional[str]:
    lower = name.lower()
    if "cash" in lower:
        return "cash"
    if "position" in lower or "posn" in lower:
        return "position"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Organize statements using metadata JSONL")
    parser.add_argument("metadata", type=str, help="Path to metadata JSONL")
    parser.add_argument("--output", type=str, required=True, help="Output directory for organized files")
    parser.add_argument("--dry-run", action="store_true", help="Only print actions without moving files")
    args = parser.parse_args()

    records = read_metadata(Path(args.metadata))
    organize_files(records, Path(args.output), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
