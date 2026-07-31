"""Shared normalization for sale-date values received from import sources."""

import re
from datetime import datetime
from typing import Any, Dict, Optional, Sequence


_ISO_DATE_TIME_FORMATS: Sequence[str] = (
    "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
)
_COMPACT_DATE_TIME_FORMATS: Sequence[str] = (
    "%Y%m%d %H:%M:%S.%f", "%Y%m%d %H:%M:%S", "%Y%m%d %H:%M",
    "%Y%m%dT%H:%M:%S.%f", "%Y%m%dT%H:%M:%S", "%Y%m%dT%H:%M",
)
_MERIDIEM_DATE_TIME_FORMATS: Sequence[str] = (
    "%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %I:%M %p",
    "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p",
)

_FORMAT_GROUPS: Dict[str, Sequence[str]] = {
    "DD/MM/YYYY": (*_MERIDIEM_DATE_TIME_FORMATS[:2], "%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%d-%m-%Y"),
    "DDmmYYYY": ("%d%m%Y",),
    "YYYYmmDD": (*_COMPACT_DATE_TIME_FORMATS, "%Y%m%d"),
    "MM/DD/YYYY": (*_MERIDIEM_DATE_TIME_FORMATS[2:], "%m/%d/%Y %H:%M:%S", "%m/%d/%Y", "%m-%d-%Y"),
    "YYYY/MM/DD": ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d"),
    "YYYY-MM-DD": (*_ISO_DATE_TIME_FORMATS, "%Y-%m-%d", "%Y/%m/%d"),
    "timestamp": _ISO_DATE_TIME_FORMATS,
}

_AUTO_FORMATS: Sequence[str] = (
    *_ISO_DATE_TIME_FORMATS,
    *_MERIDIEM_DATE_TIME_FORMATS,
    "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%d%m%Y",
    *_COMPACT_DATE_TIME_FORMATS, "%Y%m%d", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y",
    "%d-%m-%Y", "%m-%d-%Y", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d", "%Y-%d-%m",
)


def _normalize_meridiem(value: str) -> str:
    """Convert Spanish Excel/Windows AM/PM markers into strptime-compatible text."""
    normalized = value.replace("\u00a0", " ")
    normalized = re.sub(r"(?i)\ba\s*\.\s*m\s*\.?(?=\s|$)", "AM", normalized)
    normalized = re.sub(r"(?i)\bp\s*\.\s*m\s*\.?(?=\s|$)", "PM", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_sale_date(value: Any, explicit_format: Any = "auto") -> Optional[str]:
    """Normalize supported sale-date and datetime values to ``YYYY-MM-DD``."""
    if value in (None, ""):
        return None

    raw_date = _normalize_meridiem(str(value).strip().strip("'\""))
    if not raw_date:
        return None

    format_name = str(explicit_format or "auto").strip()
    for date_format in _FORMAT_GROUPS.get(format_name, _AUTO_FORMATS):
        try:
            return datetime.strptime(raw_date, date_format).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None
