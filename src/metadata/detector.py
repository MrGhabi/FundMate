#!/usr/bin/env python3
"""Statement metadata detector for uploaded broker files."""

from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional, Dict, Any, List, Iterable

from loguru import logger

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:  # pragma: no cover
    PdfReader = None

import tempfile
from src.llm_handler import LLMHandler
from src.metadata.excel_parser import ExcelMetadataExtractor
from src.pdf_processor import BROKER_CONFIG


CANONICAL_BROKER_KEYWORDS: Dict[str, List[str]] = {
    "CICC": ["CICC", "CHINA INTERNATIONAL CAPITAL"],
    "FIRST_SHANGHAI": ["FIRST SHANGHAI"],
    "GS": ["GOLDMAN", "GOLDMAN SACHS"],
    "CIS": ["CIS", "CHINA INDUSTRIAL SECURITIES", "兴证"],
    "HTI": ["HAITONG"],
    "HUATAI": ["HUATAI"],
    "IB": ["INTERACTIVEBROKERS", "INTERACTIVE BROKERS", "IBKR"],
    "LB": ["LONGBRIDGE"],
    "MOOMOO": ["MOOMOO", "FUTU"],
    "MS": ["MORGAN STANLEY"],
    "SDICS": ["SDICS"],
    "TFI": ["TFI"],
    "TIGER": ["TIGER"],
    "GSPB": ["GSPB", "GOLDMAN SACHS PB", "GS PB"],
}

BROKER_MAPPING_PROMPT = "\n".join(
    [
        "Canonical Broker Mapping:",
    ]
    + [f"- {canonical}: {', '.join(keywords)}" for canonical, keywords in CANONICAL_BROKER_KEYWORDS.items()]
)

METADATA_SYSTEM_PROMPT = (
    "You are a broker statement metadata extractor. "
    "Return a compact JSON object with BrokerName, AccountId, StatementDate (YYYY-MM-DD, e.g., 1980-07-21). "
    "BrokerName MUST use one of the following canonical names: "
    f"{', '.join(CANONICAL_BROKER_KEYWORDS.keys())}. "
    "Use null when a field is missing. Output valid JSON only.\n"
    + BROKER_MAPPING_PROMPT
)

def build_metadata_prompt(file_name: str) -> List[Dict[str, str]]:
    return [
        {
            "type": "text",
            "text": (
                f"The uploaded file name is: {file_name}. "
                "Use it only as optional context. Extract BrokerName, AccountId, StatementDate (YYYY-MM-DD) from the document itself and return JSON."
            ),
        }
    ]


@dataclass
class StatementMetadata:
    file: str
    broker_name: Optional[str]
    account_id: Optional[str]
    statement_date: Optional[str]
    source: str
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StatementMetadataDetector:
    def __init__(self, llm_handler: Optional[LLMHandler] = None, max_pdf_pages: int = 2):
        self.llm_handler = llm_handler
        self.max_pdf_pages = max_pdf_pages
        self.excel_extractor = ExcelMetadataExtractor()

    # === Public API ===
    def detect_pdf(self, path: Path) -> StatementMetadata:
        if not self.llm_handler:
            raise RuntimeError("LLM handler is required for PDF detection")

        pdf_path = self._prepare_pdf_for_detection(path)
        logger.info(f"LLM metadata extraction for PDF: {pdf_path}")
        llm_result = self.llm_handler.process_files_with_prompt(
            build_metadata_prompt(pdf_path.name),
            [str(pdf_path)],
            system_prompt=METADATA_SYSTEM_PROMPT,
        )
        broker = self._safe_get(llm_result, ["BrokerName", "broker", "broker_name"])
        account = self._safe_get(llm_result, ["AccountId", "account", "account_id"])
        stmt_date = self._normalize_date(self._safe_get(llm_result, ["StatementDate", "date"]))

        return StatementMetadata(
            file=str(path),
            broker_name=self._canonicalize_broker(broker),
            account_id=account,
            statement_date=stmt_date,
            source="llm",
            extra={"raw": llm_result},
        )

    def detect_excel(self, path: Path) -> StatementMetadata:
        logger.info(f"Metadata extraction for Excel: {path}")
        structured = self.excel_extractor.detect_metadata(path)
        if structured:
            return StatementMetadata(
                file=str(path),
                broker_name=self._canonicalize_broker(structured.broker_name),
                account_id=structured.account_id,
                statement_date=structured.statement_date,
                source="excel_structured",
                extra={},
            )
        return StatementMetadata(
            file=str(path),
            broker_name=None,
            account_id=None,
            statement_date=None,
            source="excel_structured",
            extra={"error": "No parser available"},
        )

    def detect_file(self, path: Path) -> Optional[StatementMetadata]:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return self.detect_pdf(path)
        if suffix in {".xls", ".xlsx"}:
            return self.detect_excel(path)
        logger.warning(f"Unsupported file type: {path}")
        return None

    def _prepare_pdf_for_detection(self, path: Path) -> Path:
        """Decrypt PDF into a temporary file when password is known.

        Raises when encrypted and password is unavailable to avoid futile LLM calls.
        Keeps original path if not encrypted; cleans up temp file via NamedTemporaryFile.
        """
        try:
            reader = PdfReader(str(path))
        except Exception as exc:
            logger.warning(f"Cannot open PDF {path} for decrypt check: {exc}")
            raise

        if not reader.is_encrypted:
            return path

        broker_key = path.parent.name.upper()
        password = BROKER_CONFIG.get(broker_key, {}).get("password")
        if not password:
            raise ValueError(f"Encrypted PDF without password configuration (parent folder: {broker_key})")

        try:
            decrypt_status = reader.decrypt(password)
            if decrypt_status == 0:
                raise ValueError(f"Failed to decrypt PDF with configured password for {broker_key}")
        except Exception as exc:
            raise ValueError(f"Decrypt error for {broker_key}: {exc}") from exc

        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=path.suffix)
        try:
            writer.write(tmp)
            tmp_path = Path(tmp.name)
        finally:
            tmp.close()

        logger.info(f"Decrypted PDF for metadata: {path} -> {tmp_path}")
        return tmp_path

    # === Helpers ===
    def _normalize_date(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        value = value.strip()
        # Handle ranges like "June 1, 2025 - June 30, 2025": take the last date.
        if " - " in value and any(m.isalpha() for m in value):
            parts = value.split(" - ")
            value = parts[-1].strip()

        # Try YYYY-MM-DD first
        if re.match(r"\d{4}-\d{2}-\d{2}", value):
            return value[:10]
        if re.match(r"\d{4}/\d{2}/\d{2}", value):
            parts = value.split("/")
            return f"{parts[0]}-{parts[1]}-{parts[2]}"
        if re.match(r"\d{2}/\d{2}/\d{4}", value):
            mm, dd, yyyy = value.split("/")
            return f"{yyyy}-{mm}-{dd}"
        # Month name formats: "November 26, 2025" or "Feb 28, 2025"
        month_map = {
            "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
            "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
        }
        m = re.match(r"([A-Za-z]{3,})\s+(\d{1,2}),\s*(\d{4})", value)
        if m:
            mon = month_map.get(m.group(1).upper()[:3])
            if mon:
                dd = m.group(2).zfill(2)
                yyyy = m.group(3)
                return f"{yyyy}-{mon}-{dd}"
        return value

    def _canonicalize_broker(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        stripped = value.strip().upper()
        for canonical, keywords in CANONICAL_BROKER_KEYWORDS.items():
            for keyword in keywords:
                if keyword in stripped:
                    return canonical
        return stripped

    def _safe_get(self, data: Any, keys: List[str]) -> Optional[str]:
        if isinstance(data, dict):
            for key in keys:
                if key in data and data[key]:
                    return str(data[key])
        return None


def detect_paths(paths: Iterable[Path], llm_handler: Optional[LLMHandler] = None, max_workers: int = 1) -> List[StatementMetadata]:
    """Concurrent metadata detection helper."""
    detector = StatementMetadataDetector(llm_handler=llm_handler)
    results: List[StatementMetadata] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(detector.detect_file, p): p for p in paths}
        for future in as_completed(future_map):
            path = future_map[future]
            try:
                md = future.result()
                if md:
                    results.append(md)
                    logger.info(f"[META] {path.name} -> {md.broker_name} {md.account_id} {md.statement_date}")
                else:
                    logger.warning(f"[META] {path.name} -> no metadata")
            except Exception as exc:
                logger.error(f"[META] {path.name} failed: {exc}")
    return results


def main():
    parser = argparse.ArgumentParser(description="Batch metadata detector")
    parser.add_argument("--dir", type=str, required=True, help="Directory to scan")
    parser.add_argument("--max-workers", type=int, default=1, help="Concurrency for detection")
    parser.add_argument("--only-pdf", action="store_true", help="Process only PDFs")
    parser.add_argument("--only-excel", action="store_true", help="Process only Excel")
    args = parser.parse_args()

    root = Path(args.dir)
    if not root.exists():
        parser.error(f"Directory not found: {root}")

    suffixes = set()
    if not args.only_excel:
        suffixes.add(".pdf")
    if not args.only_pdf:
        suffixes.update({".xls", ".xlsx"})

    files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in suffixes]
    logger.info(f"Scanning {len(files)} files under {root} with {args.max_workers} workers")

    llm_handler = LLMHandler() if ".pdf" in suffixes else None
    detect_paths(files, llm_handler=llm_handler, max_workers=args.max_workers)


if __name__ == "__main__":  # pragma: no cover
    main()


SKIP_PARTS = {"__MACOSX"}
SKIP_NAMES = {".DS_Store"}


def iter_files(root: Path, suffixes: Optional[List[str]] = None) -> List[Path]:
    suffixes = suffixes or [".pdf", ".xls", ".xlsx"]
    results = []
    for file in root.rglob("*"):
        if not file.is_file():
            continue
        if any(part in SKIP_PARTS for part in file.parts):
            continue
        if file.name in SKIP_NAMES or file.name.startswith("._"):
            continue
        if file.suffix.lower() in suffixes:
            results.append(file)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect broker metadata from statements")
    parser.add_argument("input", type=str, help="Directory containing extracted files")
    parser.add_argument("--output", type=str, default="metadata_report.jsonl")
    parser.add_argument("--max-files", type=int, default=None, help="Limit number of files for testing")
    args = parser.parse_args()

    input_dir = Path(args.input)
    if not input_dir.exists():
        raise SystemExit(f"Input directory not found: {input_dir}")

    try:
        llm_handler = LLMHandler()
    except Exception as exc:
        logger.error(f"Cannot initialize LLM handler: {exc}")
        raise

    detector = StatementMetadataDetector(llm_handler=llm_handler)
    files = iter_files(input_dir)
    if args.max_files:
        files = files[: args.max_files]

    logger.info(f"Processing {len(files)} files from {input_dir}")
    output_path = Path(args.output)
    with output_path.open("w", encoding="utf-8") as writer:
        for file in files:
            try:
                meta = detector.detect_file(file)
            except Exception as exc:
                logger.error(f"Failed to detect metadata for {file}: {exc}")
                meta = StatementMetadata(
                    file=str(file),
                    broker_name=None,
                    account_id=None,
                    statement_date=None,
                    source="error",
                    extra={"error": str(exc)},
                )
            if meta:
                writer.write(json.dumps(meta.to_dict(), ensure_ascii=False) + "\n")

    logger.info(f"Metadata written to {output_path}")


if __name__ == "__main__":
    main()
