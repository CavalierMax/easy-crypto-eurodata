"""Conversione rigorosa delle righe broker nel formato interno standard."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from .mapping import BrokerMapping
from .models import DataIssue, Operation, OperationType, SourceRef


EMPTY_MARKERS = {"", "none", "null", "nan", "nat"}


def _empty(value: Any) -> bool:
    if value is None or value is pd.NA:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip().casefold() in EMPTY_MARKERS


def _text(value: Any) -> str | None:
    return None if _empty(value) else str(value).strip()


def _broker(value: Any) -> str | None:
    """Restituisce la chiave canonica usata per confronti e raggruppamenti."""
    text = _text(value)
    return text.casefold() if text else None


def _decimal(value: Any, mapping: BrokerMapping, field_name: str) -> Decimal | None:
    if _empty(value):
        return None
    text = str(value).strip()
    if mapping.thousands_separator:
        text = text.replace(mapping.thousands_separator, "")
    if mapping.decimal_separator != ".":
        text = text.replace(mapping.decimal_separator, ".")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} non è un numero decimale valido: {value!r}") from exc
    if not result.is_finite():
        raise ValueError(f"{field_name} deve essere finito.")
    return result


def _date(value: Any, mapping: BrokerMapping) -> datetime:
    if _empty(value):
        raise ValueError("data mancante")
    if isinstance(value, pd.Timestamp):
        result = value.to_pydatetime()
    elif isinstance(value, datetime):
        result = value
    elif mapping.date_format:
        result = datetime.strptime(str(value).strip(), mapping.date_format)
    else:
        try:
            result = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"data non valida: {value!r}") from exc
    if result.tzinfo is None:
        if not mapping.default_timezone:
            raise ValueError("data priva di fuso orario e default_timezone non configurata")
        try:
            result = result.replace(tzinfo=ZoneInfo(mapping.default_timezone))
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"fuso orario sconosciuto: {mapping.default_timezone}") from exc
    return result.astimezone(UTC)


def normalize_row(
    row: dict[str, Any],
    mapping: BrokerMapping,
    source_file: Path,
    row_number: int,
    sheet: str | None,
) -> tuple[Operation | None, DataIssue | None]:
    """Normalizza una riga; qualsiasi anomalia diventa un errore contestualizzato."""
    source = SourceRef(source_file, row_number, sheet)

    def value(name: str) -> Any:
        source_column = mapping.columns.get(name)
        return row.get(source_column) if source_column else None

    # Un'unica forma canonica evita inventari distinti per "Kraken" e "KRAKEN".
    broker = _broker(value("broker")) or _broker(mapping.broker) or mapping.broker
    operation_id = _text(value("id_operazione")) or "<mancante>"
    try:
        raw_type = (_text(value("tipo")) or "").casefold()
        canonical_type = mapping.operation_types.get(raw_type, raw_type)
        op_type = OperationType(canonical_type)
        fee = _decimal(value("commissione_eur"), mapping, "commissione_eur") or Decimal("0")
        operation = Operation(
            date=_date(value("data"), mapping),
            broker=broker,
            type=op_type,
            asset_out=(_text(value("asset_out")) or "").upper() or None,
            quantity_out=_decimal(value("quantita_out"), mapping, "quantita_out"),
            asset_in=(_text(value("asset_in")) or "").upper() or None,
            quantity_in=_decimal(value("quantita_in"), mapping, "quantita_in"),
            value_eur=_decimal(value("valore_eur"), mapping, "valore_eur"),
            fee_eur=fee,
            operation_id=operation_id,
            source=source,
            transfer_id=_text(value("id_trasferimento")),
            destination_broker=_broker(value("broker_destinazione")),
            linked_operation_id=_text(value("id_operazione_collegata")),
        )
        return operation, None
    except (ValueError, KeyError) as exc:
        return None, DataIssue(
            code="normalizzazione",
            message=str(exc),
            broker=broker,
            operation_id=operation_id,
            source=source,
        )

