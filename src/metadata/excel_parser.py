#!/usr/bin/env python3
"""Excel metadata extractor for broker statements."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Callable

import pandas as pd
from loguru import logger
from openpyxl import load_workbook


@dataclass
class ExcelMetadata:
    broker_name: Optional[str]
    account_id: Optional[str]
    statement_date: Optional[str]


class ExcelMetadataExtractor:
    def __init__(self):
        self._parsers: Dict[str, Callable[[Path], Optional[ExcelMetadata]]] = {
            "MS": self._parse_ms,
            "GS": self._parse_gs,
            "TENFUND": self._parse_tenfund,
            "TC": self._parse_trade_confirmation,
        }

    def detect_metadata(self, path: Path) -> Optional[ExcelMetadata]:
        key = self._detect_broker_key(path)

        # Try: preferred parser first (if detected), then fall back to all parsers.
        ordered_keys = []
        if key:
            ordered_keys.append(key)
        ordered_keys.extend(k for k in self._parsers if k not in ordered_keys)

        for parser_key in ordered_keys:
            parser = self._parsers[parser_key]
            try:
                result = parser(path)
            except Exception as exc:
                logger.warning(f"Excel metadata parser failed for {path} using {parser_key}: {exc}")
                continue
            if result:
                return result
        return None

    def _detect_broker_key(self, path: Path) -> Optional[str]:
        name = path.name.lower()
        if "tenfund" in name or "ten fund" in name:
            return "TENFUND"
        if "gs" in name or "goldman" in name:
            return "GS"
        if "ms" in name or "morgan" in name:
            return "MS"
        if "trade confirmation" in name:
            return "TC"
        return None

    def _parse_ms(self, path: Path) -> Optional[ExcelMetadata]:
        df = pd.read_excel(path, sheet_name=0, header=None, nrows=40)
        stmt_candidate = df.iloc[2, 1] if df.shape[0] > 2 and df.shape[1] > 1 else None
        stmt_date = self._normalize_date(str(stmt_candidate)) if pd.notna(stmt_candidate) else None

        account = None
        search_region = df.iloc[:15, :5]
        for value in search_region.values.flatten():
            if isinstance(value, str) and ("A/C" in value.upper() or "ACCOUNT" in value.upper()):
                match = re.search(r'([A-Z0-9]{4,})', value)
                if match:
                    account = match.group(1)
                    break
        return ExcelMetadata("MORGAN STANLEY", account, stmt_date)

    def _parse_gs(self, path: Path) -> Optional[ExcelMetadata]:
        df = pd.read_excel(path, header=None, nrows=40)
        account = None
        stmt_date = None
        for value in df.values.flatten():
            if isinstance(value, str):
                upper = value.upper()
                if "ACCOUNT" in upper or "A/C" in upper:
                    match = re.search(r'\(([A-Z0-9]+)\)', value)
                    if not match:
                        match = re.search(r'([A-Z0-9]{6,})', value)
                    if match:
                        account = match.group(1)
                if "VALUATION DATE" in upper or re.search(r'\d{2}-[A-Za-z]{3}-\d{4}', value):
                    stmt_date = self._normalize_date(value.split(":")[-1].strip())
            elif isinstance(value, datetime):
                stmt_date = value.strftime("%Y-%m-%d")
            elif isinstance(value, (int, float)) and not account:
                digits = str(value).replace(".0", "")
                if digits.isdigit():
                    account = digits
        return ExcelMetadata("GOLDMAN SACHS", account, stmt_date)

    def _parse_tenfund(self, path: Path) -> Optional[ExcelMetadata]:
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        stmt_date = None
        for row in ws.iter_rows(min_row=1, max_row=40, max_col=5):
            for cell in row:
                value = cell.value
                if isinstance(value, datetime):
                    stmt_date = value.strftime("%Y-%m-%d")
                    break
            if stmt_date:
                break
        wb.close()
        return ExcelMetadata("TEN FUND", None, stmt_date)

    def _parse_trade_confirmation(self, path: Path) -> Optional[ExcelMetadata]:
        # Minimal TC support: infer date from filename first; fall back to sheet inspection.
        name = path.name
        stmt_date = None

        # 1) Try filename patterns: 20250807 / 2025-08-07 / 2025_08_07.
        m = re.search(r"(20\d{2})[-_/]?(\d{2})[-_/]?(\d{2})", name)
        if m:
            stmt_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

        # 2) Inspect top rows for datetime or date-like strings if still unknown.
        if not stmt_date:
            df = pd.read_excel(path, sheet_name=0, header=None, nrows=30)
            for value in df.values.flatten():
                if isinstance(value, datetime):
                    stmt_date = value.strftime("%Y-%m-%d")
                    break
                if isinstance(value, str):
                    norm = self._normalize_date(value)
                    if norm and re.match(r"\d{4}-\d{2}-\d{2}", norm):
                        stmt_date = norm[:10]
                        break

        return ExcelMetadata("TC", None, stmt_date)

    def _normalize_date(self, value: str) -> Optional[str]:
        if not value:
            return None
        value = value.strip()
        if "-" in value and len(value) >= 10:
            try:
                dt = datetime.strptime(value.strip()[:11], "%d-%b-%Y")
                return dt.strftime("%Y-%m-%d")
            except Exception:
                return value[:10]
        if "/" in value:
            parts = value.split("/")
            if len(parts) == 3:
                if len(parts[0]) == 4:
                    return f"{parts[0]}-{parts[1]}-{parts[2][:2]}"
                return f"{parts[2][:4]}-{parts[0]}-{parts[1]}"
        if " " in value and ',' in value:
            try:
                dt = datetime.strptime(value[:12], "%b %d, %Y")
                return dt.strftime("%Y-%m-%d")
            except Exception:
                pass
        return value
