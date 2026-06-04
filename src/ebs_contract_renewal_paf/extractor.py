"""
================================================================================
 Syntax Corporation © 2026 — All Rights Reserved
--------------------------------------------------------------------------------
 Project : EBS Contract Renewal PAF — BPA Renewal Automation Agent
 Module  : extractor.py — renewal-quote field extraction
 Version : 1.0.0      Build : 2026.06.04      Date : 2026-06-04
--------------------------------------------------------------------------------
 Two extraction strategies behind one protocol:

   * DeterministicExtractor — pure-Python regex/Decimal parser for the
     structured supplier renewal-quote text format. NO external dependencies, so
     the whole pipeline runs end-to-end with ONLY EBSDB available. The line
     table is pipe-delimited so multi-word item names ("Thermostat - Cooling")
     parse unambiguously.
   * LLMExtractor — optional Anthropic-backed extractor for messy/scanned
     quotes; used only when ANTHROPIC_API_KEY is set and selected.

 make_extractor() picks the right one based on settings.
================================================================================
"""

from __future__ import annotations

import json
import os
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol


class ExtractionError(ValueError):
    """Raised when a renewal quote cannot be parsed into the expected shape."""


class RenewalExtractor(Protocol):
    def extract(self, quote_text: str) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _money(text: str) -> Decimal:
    """Parse a money token like '6,250.00' or '$1,755.00' to Decimal."""
    cleaned = text.replace(",", "").replace("$", "").strip()
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ExtractionError(f"Not a number: {text!r}") from exc


def _number(text: str) -> Decimal:
    cleaned = re.sub(r"[^\d.\-]", "", text.strip())
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ExtractionError(f"Not a number: {text!r}") from exc


# ---------------------------------------------------------------------------
# Deterministic extractor
# ---------------------------------------------------------------------------

class DeterministicExtractor:
    """Parse the structured renewal-quote text format used by this project.

    Expected (tolerant) layout:
        <Supplier name>                       (first substantive line)
        Quote Number:        <str>
        Quote Date:          <YYYY-MM-DD>
        Existing Agreement:  <str>            (the BPA segment1 / number)
        Currency:            <ISO|optional, default USD>
        Federal Tax ID:      <str|optional>
        Proposed Term Start: <YYYY-MM-DD>
        Proposed Term End:   <YYYY-MM-DD>
        <pipe-delimited line table>:
            LINE | ITEM | EST_QTY | NEW_UNIT_PRICE
            1    | AC Filter | 200 | 17.50
    """

    _FIELD_PATTERNS = {
        "quote_number": r"Quote\s*(?:Number|No\.?|#)\s*:?\s*(\S+)",
        "quote_date": r"Quote\s*Date\s*:?\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
        # Anchored to a labelled line + ':' so it never matches a stray token.
        "agreement_num": r"^[ \t]*(?:Existing\s+)?(?:Blanket\s+)?Agreement"
                         r"(?:\s*(?:#|No\.?|Number|Ref(?:erence)?))?\s*:\s*(\S+)",
        "currency": r"Currency\s*:?\s*([A-Z]{3})",
        "vendor_tax_id": r"(?:Federal\s*)?Tax\s*ID\s*:?\s*([0-9\-]+)",
        "new_effective_date":
            r"(?:Proposed\s+)?(?:Term\s+|Effective\s+|Renewal\s+)"
            r"(?:Start|Effective|From)\s*(?:Date)?\s*:?\s*"
            r"([0-9]{4}-[0-9]{2}-[0-9]{2})",
        "new_expiration_date":
            r"(?:Proposed\s+)?(?:Term\s+|Expiration\s+|Renewal\s+)"
            r"(?:End|Expiration|To|Through)\s*(?:Date)?\s*:?\s*"
            r"([0-9]{4}-[0-9]{2}-[0-9]{2})",
    }

    # A pipe-delimited row: <line_no> | <item...> | <qty> | <unit_price>
    _LINE_RE = re.compile(
        r"^\s*(\d+)\s*\|\s*(.+?)\s*\|\s*([\d,]+(?:\.\d+)?)\s*\|\s*\$?([\d,]+(?:\.\d+)?)\s*$"
    )

    def extract(self, quote_text: str) -> dict[str, Any]:
        text = quote_text
        result: dict[str, Any] = {}

        for key, pat in self._FIELD_PATTERNS.items():
            m = re.search(pat, text, re.I | re.M)
            result[key] = m.group(1) if m else None

        if not result.get("agreement_num"):
            raise ExtractionError(
                "Could not find the existing agreement number "
                "(expected a line like 'Existing Agreement: 4467').")
        if not result.get("quote_number"):
            raise ExtractionError("Could not find a quote number.")

        result["currency"] = result.get("currency") or "USD"
        result["vendor_name"] = self._vendor_name(text)

        # line items
        lines: list[dict[str, Any]] = []
        for raw in text.splitlines():
            lm = self._LINE_RE.match(raw)
            if not lm:
                continue
            line_no = int(lm.group(1))
            item = lm.group(2).strip()
            qty = _number(lm.group(3))
            new_price = _money(lm.group(4))
            lines.append({
                "line_number": line_no,
                "item_number": item,
                # convention: quote line N ↔ agreement line N
                "agreement_line_num": line_no,
                "estimated_qty": float(qty),
                "new_unit_price": float(new_price),
            })
        if not lines:
            raise ExtractionError(
                "No renewal line items could be parsed (expected pipe-delimited "
                "rows: 'LINE | ITEM | EST_QTY | NEW_UNIT_PRICE').")
        result["lines"] = lines

        # informational rollup of the proposed annual value
        result["proposed_total"] = float(
            sum((Decimal(str(l["new_unit_price"])) * Decimal(str(l["estimated_qty"]))
                 for l in lines), Decimal("0")))
        return result

    @staticmethod
    def _vendor_name(text: str) -> str:
        """The supplier name is the first substantive line of the document."""
        for raw in text.splitlines():
            s = raw.strip(" =\t")
            if not s:
                continue
            if re.fullmatch(r"[=\-_]+", s):
                continue
            return s
        raise ExtractionError("Could not determine vendor name.")


# ---------------------------------------------------------------------------
# Optional LLM extractor (Anthropic)
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT = """You are a procurement contract-renewal extractor. Read
the supplier blanket-agreement renewal quote below and return ONLY a JSON object
with this shape:
{"vendor_name": str, "vendor_tax_id": str|null, "quote_number": str,
 "quote_date": "YYYY-MM-DD"|null, "agreement_num": str, "currency": str,
 "new_effective_date": "YYYY-MM-DD", "new_expiration_date": "YYYY-MM-DD",
 "lines": [{"line_number": int, "item_number": str|null,
 "agreement_line_num": int|null, "estimated_qty": number,
 "new_unit_price": number}]}
No preamble, no markdown fences. Use null for genuinely absent fields; never invent values.

RENEWAL QUOTE TEXT:
---
"""


class LLMExtractor:
    """Anthropic-backed extractor (optional). Requires the `anthropic` package
    and ANTHROPIC_API_KEY."""

    def __init__(self, model: str = "claude-opus-4-8"):
        try:
            from anthropic import Anthropic
        except ImportError as exc:  # pragma: no cover - optional dep
            raise ExtractionError(
                "LLMExtractor requires the 'anthropic' package."
            ) from exc
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise ExtractionError("ANTHROPIC_API_KEY is not set.")
        self._client = Anthropic()
        self.model = model

    def extract(self, quote_text: str) -> dict[str, Any]:  # pragma: no cover
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=2000,
            messages=[{"role": "user",
                       "content": _EXTRACTION_PROMPT + quote_text}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw
            if raw.lstrip().startswith("json"):
                raw = raw.lstrip()[4:]
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ExtractionError(f"LLM did not return valid JSON: {exc}") from exc


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def make_extractor(strategy: str = "deterministic",
                   llm_model: str = "claude-opus-4-8") -> RenewalExtractor:
    """Build an extractor.

    strategy:
      'deterministic' -> always the regex parser (default; zero deps)
      'llm'           -> Anthropic (raises if unavailable)
      'auto'          -> LLM when ANTHROPIC_API_KEY is set, else deterministic
    """
    if strategy == "deterministic":
        return DeterministicExtractor()
    if strategy == "llm":
        return LLMExtractor(model=llm_model)
    if strategy == "auto":
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                return LLMExtractor(model=llm_model)
            except ExtractionError:
                return DeterministicExtractor()
        return DeterministicExtractor()
    raise ValueError(f"Unknown extractor strategy: {strategy!r}")
