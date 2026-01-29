#!/usr/bin/env python3
"""
Organize statement files into canonical naming based on metadata JSONL.

Developer Notes (migrated from docs/src/metadata/organizer.py.md):
- Moves statement files into a canonical archive layout keyed by broker/date/account and avoids overwrites via variant naming.
- Computes SHA-256 hashes (when archiving into `data/archives`) to de-duplicate identical content.
- Special-cases some brokers (e.g., GSPB) that ship separate cash/position workbooks and merges them into a single Excel.
- CLI consumes JSONL produced by `src.metadata.detector` and writes the organized outputs into the requested directory.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from shutil import move
from typing import Optional, Dict, List, Tuple

from loguru import logger
import hashlib
import re
import pandas as pd


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
    # ==== GSPB pre-merge: combine Position + Cash Excel into a single workbook per broker/date/account ====
    merged_records: List[MetadataRecord] = []
    records_to_skip: set[Tuple[Path, Optional[str], Optional[str], Optional[str]]] = set()

    # Group by (broker_name, statement_date). Account ID is excluded to avoid mixing multi-account variants.
    groups: Dict[Tuple[Optional[str], Optional[str]], List[MetadataRecord]] = {}
    for record in records:
        key = (record.broker_name, record.statement_date)
        groups.setdefault(key, []).append(record)

    for (broker, stmt_date), group_records in groups.items():
        if broker != "GSPB":
            continue
        if not stmt_date:
            logger.warning("GSPB merge skipped: missing statement_date for group of %s files", len(group_records))
            for r in group_records:
                records_to_skip.add((r.file, r.broker_name, r.account_id, r.statement_date))
            continue

        excel_records = [
            r for r in group_records
            if r.file.suffix.lower() in {".xls", ".xlsx"}
        ]
        if not excel_records:
            continue

        # Detect Position/Cash by sheet headers; do not rely on filename/account_id.
        def _detect_kind(path: Path) -> str:
            try:
                import pandas as pd
                df = pd.read_excel(path, sheet_name=0, header=None, nrows=12, dtype=str)
            except Exception:
                try:
                    import xlrd3 as xlrd  # type: ignore
                    xlrd.sheet.Sheet.handle_note = lambda self, data, txos: None  # type: ignore
                    book = xlrd.open_workbook(path)
                    sh = book.sheet_by_index(0)
                    rows = [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(min(sh.nrows, 12))]
                    import pandas as pd
                    df = pd.DataFrame(rows)
                except Exception:
                    return "unknown"

            upper_rows = [str(v).upper() for v in df.values.flatten() if str(v) != 'nan']
            if any("CUSTODY POSITION AP" in v for v in upper_rows):
                return "pos"
            if any("CUSTODY CASH BALANCES BY ACCOUNT AND ACCOUNT TYPE" in v for v in upper_rows):
                return "cash"
            return "unknown"

        pos_records = []
        cash_records = []
        unknown_records = []
        for r in excel_records:
            kind = _detect_kind(r.file)
            if kind == "pos":
                pos_records.append(r)
            elif kind == "cash":
                cash_records.append(r)
            else:
                unknown_records.append(r)

        # Whole-group rule: if a date does not have exactly 1 position file and 1 cash file, skip the merge.
        if not (len(pos_records) == 1 and len(cash_records) == 1):
            logger.warning(
                "GSPB merge skipped for %s: require exactly 1 pos + 1 cash in this date (P=%s, C=%s, U=%s). Files kept for manual handling.",
                stmt_date, len(pos_records), len(cash_records), len(unknown_records)
            )
            for r in excel_records:
                records_to_skip.add((r.file, r.broker_name, r.account_id, r.statement_date))
            continue

        pos_rec = pos_records[0]
        cash_rec = cash_records[0]
        acct_label = cash_rec.account_id or pos_rec.account_id or "UNKNOWN"

        try:
            merged_path = _merge_gspb_excels(
                pos_rec.file,
                cash_rec.file,
                acct_label,
                stmt_date,
            )
        except Exception as exc:
            logger.error(f"Failed to merge GSPB Excel files for {acct_label} {stmt_date}: {exc}")
            continue

        merged_record = MetadataRecord(
            file=merged_path,
            broker_name="GSPB",
            account_id=acct_label,
            statement_date=stmt_date,
        )
        merged_records.append(merged_record)

        for r in excel_records:
            records_to_skip.add((r.file, r.broker_name, r.account_id, r.statement_date))

        logger.info(
            f"GSPB position+cash merged for date {stmt_date}: "
            f"{pos_rec.file.name} + {cash_rec.file.name} -> {merged_path.name}"
        )

    final_records: List[MetadataRecord] = []
    for record in records:
        key = (record.file, record.broker_name, record.account_id, record.statement_date)
        if key in records_to_skip:
            continue
        final_records.append(record)
    final_records.extend(merged_records)

    # ==== Normal organize flow (using potentially merged records) ====
    for record in final_records:
        target_name = record.canonical_filename()
        if not target_name:
            logger.warning(f"Skipping {record.file} due to missing broker/date")
            continue

        broker_dir = output_dir / record.broker_name
        # TC special-case: normalize canonical filename to TC-YYYY-MM-DD-<account> to match TC parser expectations
        if record.broker_name == "TC" and target_name.startswith("TC_"):
            target_name = target_name.replace("TC_", "TC-", 1)
        target_path = broker_dir / target_name

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


def _merge_gspb_excels(position_path: Path, cash_path: Path, account_id: str, stmt_date: str) -> Path:
    """
    Merge GSPB Position + Cash Excel files into a single workbook.

    The merged workbook is created alongside the original files and later moved
    into data/archives by organize_files. Sheet names are preserved where possible;
    duplicates are suffixed to avoid collisions.
    """
    parent = position_path.parent
    merged_name = f"GSPB_{stmt_date}_{account_id}_merged.xlsx"
    merged_path = parent / merged_name

    # Avoid overwriting existing merged file
    counter = 1
    while merged_path.exists():
        merged_name = f"GSPB_{stmt_date}_{account_id}_merged_v{counter}.xlsx"
        merged_path = parent / merged_name
        counter += 1

    def _read_all_sheets(path: Path) -> Dict[str, pd.DataFrame]:
        # Prefer robust xlrd3/xlrd fallback for old .xls (mirrors excel_parser)
        try:
            try:
                import xlrd3 as xlrd  # type: ignore
            except ImportError:  # pragma: no cover
                import xlrd  # type: ignore

            # Patch handle_note to avoid assertion failures on comment records
            try:
                xlrd.sheet.Sheet.handle_note = lambda self, data, txos: None  # type: ignore
            except Exception:
                pass

            book = xlrd.open_workbook(path)
            sheets_dict: Dict[str, pd.DataFrame] = {}
            for name in book.sheet_names():
                sh = book.sheet_by_name(name)
                rows = [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)]
                sheets_dict[name] = pd.DataFrame(rows)
            return sheets_dict
        except Exception:
            pass

        # Fallback to pandas engine for xlsx or when xlrd path fails
        try:
            return pd.read_excel(path, sheet_name=None, header=None)
        except Exception as exc:
            logger.error(f"Failed to read Excel for merge: {path} ({exc})")
            raise

    sheets: List[Tuple[str, pd.DataFrame]] = []

    # Position workbook sheets come first, keep original sheet names
    for name, df in _read_all_sheets(position_path).items():
        sheet_name = str(name) if name else "Sheet1"
        sheets.append((sheet_name, df))

    # Cash workbook sheets appended; suffix to minimize name collisions
    for name, df in _read_all_sheets(cash_path).items():
        base_name = str(name) if name else "Sheet1"
        sheet_name = f"{base_name}_cash"
        sheets.append((sheet_name, df))

    existing_names = set()
    with pd.ExcelWriter(merged_path, engine="openpyxl") as writer:
        for sheet_name, df in sheets:
            base = sheet_name or "Sheet"
            name = base
            idx = 2
            while name in existing_names:
                name = f"{base}_{idx}"
                idx += 1
            df.to_excel(writer, sheet_name=name, index=False, header=False)
            existing_names.add(name)

    return merged_path


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
