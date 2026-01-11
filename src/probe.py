"""
Lightweight probe logger for pipeline runs.
Collects per-broker files/metrics and global timing, writes to temp for analysis.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger

_lock = threading.RLock()
_enabled = False
_data: Dict[str, object] = {}
_output_path: Optional[Path] = None
_on_update = None


def is_enabled() -> bool:
    return _enabled


def start(date: str, use_tc: bool, archive_dir: str, tc_dir: Optional[str], output_path: Path, job_id: Optional[str] = None, on_update=None) -> None:
    """
    Initialize probe collection.
    """
    global _enabled, _data, _output_path, _on_update
    enable_flag = os.getenv("PIPELINE_PROBE_ENABLE", "0") == "1"
    if not enable_flag:
        _enabled = False
        _data = {}
        _output_path = None
        _on_update = None
        logger.info("[pipeline-probe] disabled (set PIPELINE_PROBE_ENABLE=1 to enable)")
        return

    _enabled = True
    _on_update = on_update
    _output_path = Path(output_path) if output_path else None
    _data = {
        "global": {
            "date": date,
            "use_tc": use_tc,
            "archive_dir": archive_dir,
            "tc_dir": tc_dir,
            "job_id": job_id,
            "started_at": datetime.utcnow().isoformat() + "Z",
        },
        "brokers": {},
    }
    logger.info("[pipeline-probe] enabled for job {} (date={})", job_id, date)


def add_file_counts(pdf_count: int = 0, excel_count: int = 0) -> None:
    if not _enabled:
        return
    with _lock:
        counts = _data.setdefault("global", {}).setdefault("file_counts", {"pdf": 0, "excel": 0})
        counts["pdf"] = counts.get("pdf", 0) + int(pdf_count)
        counts["excel"] = counts.get("excel", 0) + int(excel_count)


def record_files(broker: str, files: List[Path], kind: str) -> None:
    """
    Record file list for a broker by type (pdf/excel).
    """
    if not _enabled:
        return
    kind = "pdf" if kind.lower().startswith("pdf") else "excel"
    with _lock:
        b = _data.setdefault("brokers", {}).setdefault(broker, {"files": {"pdf": [], "excel": []}})
        existing = set(b["files"][kind])
        for f in files:
            try:
                p = str(f)
            except Exception:
                continue
            if p not in existing:
                b["files"][kind].append(p)
                existing.add(p)


def mark_broker_start(broker: str) -> None:
    if not _enabled:
        return
    with _lock:
        b = _data.setdefault("brokers", {}).setdefault(broker, {"files": {"pdf": [], "excel": []}})
        if "started_at" not in b:
            b["started_at"] = datetime.utcnow().isoformat() + "Z"


def mark_broker_end(broker: str, status: str = "completed", error: Optional[str] = None) -> None:
    if not _enabled:
        return
    progress_payload: Optional[Tuple[int, str]] = None
    with _lock:
        b = _data.setdefault("brokers", {}).setdefault(broker, {"files": {"pdf": [], "excel": []}})
        b["finished_at"] = datetime.utcnow().isoformat() + "Z"
        b["status"] = status
        if error:
            b["error"] = error
        progress_payload = _compute_progress()
    _push_progress(progress_payload, message=f"{broker} {status}")


def set_broker_financials(broker: str, cash: Optional[Dict[str, float]] = None, positions_value_usd: Optional[float] = None) -> None:
    if not _enabled:
        return
    with _lock:
        b = _data.setdefault("brokers", {}).setdefault(broker, {"files": {"pdf": [], "excel": []}})
        if cash is not None:
            b["cash"] = cash
        if positions_value_usd is not None:
            b["positions_value_usd"] = positions_value_usd


def get_brokers() -> List[str]:
    if not _enabled:
        return []
    with _lock:
        return list(_data.get("brokers", {}).keys())


def get_data() -> Dict[str, object]:
    """
    Return a deep-ish copy for attachment to job result without mutating internal state.
    """
    if not _enabled:
        return {}
    with _lock:
        import copy
        return copy.deepcopy(_data)


def set_tc_files(tc_files: List[str]) -> None:
    if not _enabled:
        return
    with _lock:
        _data.setdefault("global", {})["tc_files"] = tc_files


def finalize(success: bool = True, error: Optional[str] = None, elapsed_ms: Optional[int] = None) -> None:
    if not _enabled:
        return
    progress_payload: Optional[Tuple[int, str]] = None
    with _lock:
        global_finished = datetime.utcnow().isoformat() + "Z"
        _data.setdefault("global", {})["finished_at"] = global_finished
        if elapsed_ms is not None:
            _data["global"]["elapsed_ms"] = elapsed_ms
        _data["global"]["status"] = "success" if success else "failed"
        if error:
            _data["global"]["error"] = error

        # Mark brokers without status as unknown
        for broker, payload in _data.get("brokers", {}).items():
            payload.setdefault("status", "unknown")

        progress_payload = _compute_progress(force_complete=True)

        snapshot = None
        if _output_path:
            try:
                _output_path.parent.mkdir(parents=True, exist_ok=True)
                snapshot = json.dumps(_data, indent=2)
            except Exception as e:
                logger.warning("[pipeline-probe] failed to serialize probe data: {}", e)
                snapshot = None

    _push_progress(progress_payload)

    if _output_path and snapshot:
        try:
            with _output_path.open("w", encoding="utf-8") as f:
                f.write(snapshot)
            logger.info("[pipeline-probe] wrote probe file: {}", _output_path)
        except Exception as e:
            logger.warning("[pipeline-probe] failed to write probe file {}: {}", _output_path, e)

    # reset state to avoid cross-run contamination
    with _lock:
        _enabled = False
        _data = {}
        _output_path = None
        _on_update = None


def _compute_progress(force_complete: bool = False) -> Tuple[int, str]:
    brokers = _data.get("brokers", {})
    total = len(brokers)
    completed = len([b for b in brokers.values() if b.get("status") == "completed"])
    if total == 0:
        progress = 10
    else:
        progress = 10 + int(completed / total * 80)
    if force_complete:
        progress = 100
    return progress, f"{completed}/{total} brokers completed"


def _push_progress(payload: Optional[Tuple[int, str]], message: Optional[str] = None) -> None:
    """
    Invoke on_update callback with a derived progress based on broker completion.
    payload: (progress, default_message)
    """
    if not _enabled or _on_update is None or payload is None:
        return
    progress, default_message = payload
    try:
        _on_update(progress, message or default_message)
    except Exception:
        # swallow to avoid breaking main flow
        return
