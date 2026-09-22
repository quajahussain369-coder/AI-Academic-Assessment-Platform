"""Deterministic value normalization helpers for the V2.4 Normalizer.

Each helper returns a :class:`NormalizedValue` that always preserves the
original ``raw`` cell value.  The ``kind`` of the result describes the
*data type* of the value (mark, percentage, grade, status, blank, ...).

The important distinction: a raw number is not automatically a mark, and
a number <= 1 is not automatically a percentage fraction.  The helpers
that convert a fraction to a full percentage are only ever invoked by the
normalizer for columns whose Phase 2 semantics prove the percentage
reading - never by ``normalize_mark`` or generic text helpers.

Status tokens (``AB``, ``Absent``, ``EX``, ``Exempt``) are never turned
into zeros.  Unknown status-like strings stay ``unresolved`` rather than
being invented into a known status.
"""

from typing import Any, Dict, Optional

from assessment_engine.intelligent_import.normalizer.models import (
    NormalizedValue,
    VALUE_BLANK,
    VALUE_GRADE,
    VALUE_IDENTIFIER,
    VALUE_MARK,
    VALUE_MEASURE,
    VALUE_PERCENTAGE,
    VALUE_RESULT,
    VALUE_STATUS,
    VALUE_TEXT,
    VALUE_TOTAL,
    VALUE_UNRESOLVED,
    VALUE_ZERO,
)

_STATUS_ABSENT = "absent"
_STATUS_EXEMPT = "exempt"

_ABSENT_TOKENS = {"a", "ab", "absent", "abs"}
_EXEMPT_TOKENS = {"e", "ex", "exempt"}

_DASH_TOKENS = {"-", "--", "—", "–"}


def clean_text(value) -> str:
    """Stable text form: whitespace-trimmed, integers without a ``.0``."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def parse_number(value) -> Optional[float]:
    """Parse a numeric cell (int/float or numeric string); None otherwise."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _is_dash(value) -> bool:
    return isinstance(value, str) and value.strip() in _DASH_TOKENS


def _blank(value) -> NormalizedValue:
    return NormalizedValue(VALUE_BLANK, value, None, note="blank cell")


def _dash(value) -> NormalizedValue:
    return NormalizedValue(
        VALUE_BLANK, value, None, note="dash placeholder treated as blank"
    )


def _status(value, status: str) -> NormalizedValue:
    return NormalizedValue(
        VALUE_STATUS,
        value,
        status,
        note=f"academic status token {value!r} mapped to {status!r} (not a zero)",
    )


def _unresolved(value, explanation: str) -> NormalizedValue:
    return NormalizedValue(
        VALUE_UNRESOLVED, value, None, note=explanation
    )


# ------------------------------------------------------------
# Status recognition
# ------------------------------------------------------------


def normalize_status(value) -> Optional[str]:
    """Return the canonical status for a status token, else None.

    ``AB``/``Absent`` -> ``absent``; ``EX``/``Exempt`` -> ``exempt``.
    Only exactly known tokens map to a status; anything else stays None so
    the caller can decide how to treat it (text, unresolved, ...).
    """
    if not isinstance(value, str):
        return None
    token = value.strip().lower()
    if token in _ABSENT_TOKENS:
        return _STATUS_ABSENT
    if token in _EXEMPT_TOKENS:
        return _STATUS_EXEMPT
    return None


# ------------------------------------------------------------
# Per-kind normalizers
# ------------------------------------------------------------


def normalize_text(value) -> NormalizedValue:
    """A cleaned text value (names, labels, free text)."""
    if is_blank(value):
        return _blank(value)
    return NormalizedValue(
        VALUE_TEXT, value, clean_text(value), note="text value"
    )


def normalize_identifier(value) -> NormalizedValue:
    """A stable identifier (roll number, registration number, serial)."""
    if is_blank(value):
        return _blank(value)
    return NormalizedValue(
        VALUE_IDENTIFIER, value, clean_text(value), note="identifier value"
    )


def normalize_mark(value) -> NormalizedValue:
    """A mark cell: status tokens, explicit zeros and numeric marks.

    ``AB``/``Absent``/``Exempt`` become ``status`` values, never zero.
    Dash placeholders become blank; unrecognized values stay unresolved.
    """
    if is_blank(value):
        return _blank(value)
    if _is_dash(value):
        return _dash(value)
    status = normalize_status(value)
    if status is not None:
        return _status(value, status)
    number = parse_number(value)
    if number is None:
        return _unresolved(
            value, "value is not a parseable mark nor a known status token"
        )
    if number == 0:
        return NormalizedValue(
            VALUE_ZERO, value, 0.0, note="explicit zero, preserved as such"
        )
    return NormalizedValue(
        VALUE_MARK, value, number, note="numeric mark value"
    )


def normalize_percentage(value) -> NormalizedValue:
    """A percentage on the 0-100 scale, from 69%, 69, 69.0, 0.69, ...

    ``69%`` keeps its explicit percent suffix.  A numeric value in
    ``(0, 1]`` is a fraction of 100 (the spreadsheet percentage-cell
    convention) and is scaled to the 0-100 scale; values greater than 1
    are already on that scale.  The raw value is always preserved so
    ``0.69`` and ``69`` remain distinguishable.
    """
    if is_blank(value):
        return _blank(value)
    if _is_dash(value):
        return _dash(value)
    status = normalize_status(value)
    if status is not None:
        return _status(value, status)

    number = None
    note = ""
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("%"):
            inner = parse_number(text[:-1].strip())
            if inner is not None:
                number = inner
                note = "value given with an explicit '%' suffix"

    if number is None:
        number = parse_number(value)
        if number is None:
            return _unresolved(value, "value is not a parseable percentage")

    if 0 < number <= 1.0:
        number = round(number * 100.0, 4)
        note = note or "0 < value <= 1 interpreted as a fraction of 100"

    if number == 0:
        return NormalizedValue(
            VALUE_ZERO, value, 0.0, note=note or "explicit zero percentage"
        )
    return NormalizedValue(
        VALUE_PERCENTAGE,
        value,
        float(number),
        note=note or "percentage value already on the 0-100 scale",
    )


def normalize_total(value) -> NormalizedValue:
    """A total score, including ``69/100`` fraction strings.

    ``69/100`` keeps the obtained component as ``normalized`` and the
    maximum in ``extra``.
    """
    if is_blank(value):
        return _blank(value)
    if _is_dash(value):
        return _dash(value)
    status = normalize_status(value)
    if status is not None:
        return _status(value, status)

    if isinstance(value, str):
        parts = value.strip().split("/")
        if len(parts) == 2:
            obtained = parse_number(parts[0])
            maximum = parse_number(parts[1])
            if obtained is not None and maximum is not None:
                return NormalizedValue(
                    VALUE_TOTAL,
                    value,
                    float(obtained),
                    note=f"fraction '{value.strip()}' kept as its obtained component",
                    extra={"maximum": float(maximum)},
                )

    number = parse_number(value)
    if number is None:
        return _unresolved(value, "value is not a parseable total")
    if number == 0:
        return NormalizedValue(
            VALUE_ZERO, value, 0.0, note="explicit zero total"
        )
    return NormalizedValue(
        VALUE_TOTAL, value, float(number), note="total marks value"
    )


def normalize_grade(value) -> NormalizedValue:
    """A letter/numeric grade.

    Grades are deliberately NOT routed through status tokens: in a grade
    column, ``A`` is a grade, not an absence marker.  The value is kept as
    text when it is not numeric.
    """
    if is_blank(value):
        return _blank(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            return NormalizedValue(
                VALUE_GRADE, value, cleaned, note="grade value (letter or point)"
            )
    number = parse_number(value)
    if number is not None:
        return NormalizedValue(
            VALUE_GRADE, value, float(number), note="grade value recorded as a number"
        )
    return _unresolved(value, "value is not a recognizable grade")


def normalize_result(value) -> NormalizedValue:
    """A pass/fail style outcome (Result / Status columns)."""
    if is_blank(value):
        return _blank(value)
    if _is_dash(value):
        return _dash(value)
    cleaned = clean_text(value)
    if not cleaned:
        return _unresolved(value, "blank-looking result value")
    return NormalizedValue(
        VALUE_RESULT, value, cleaned, note="result/status outcome"
    )


def normalize_measure(value, *, label: str = "measure") -> NormalizedValue:
    """A generic numeric/text measure (average, rank, attendance, ...)."""
    if is_blank(value):
        return _blank(value)
    if _is_dash(value):
        return _dash(value)
    number = parse_number(value)
    if number is not None:
        return NormalizedValue(
            VALUE_MEASURE, value, float(number), note=f"{label} numeric value"
        )
    if isinstance(value, str) and value.strip():
        return NormalizedValue(
            VALUE_MEASURE,
            value,
            value.strip(),
            note=f"{label} recorded as text",
        )
    return _unresolved(value, f"value is not a recognizable {label}")