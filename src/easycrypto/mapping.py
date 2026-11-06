"""Configurazione dichiarativa dei formati esportati dai broker."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


STANDARD_FIELDS = {
    "data",
    "broker",
    "tipo",
    "asset_out",
    "quantita_out",
    "asset_in",
    "quantita_in",
    "valore_eur",
    "commissione_eur",
    "id_operazione",
    "id_trasferimento",
    "broker_destinazione",
    "id_operazione_collegata",
}


@dataclass(frozen=True, slots=True)
class BrokerMapping:
    broker: str
    columns: dict[str, str]
    operation_types: dict[str, str] = field(default_factory=dict)
    date_format: str | None = None
    default_timezone: str | None = None
    csv_separator: str = ","
    csv_encoding: str = "utf-8-sig"
    decimal_separator: str = "."
    thousands_separator: str | None = None
    excel_sheet: str | int | None = 0


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"La chiave YAML '{name}' deve essere una mappatura.")
    return value


def load_broker_mapping(path: str | Path) -> BrokerMapping:
    """Carica e valida un mapping YAML, senza includere logica broker nel codice."""
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Il file YAML deve contenere una mappatura alla radice.")
    broker = str(raw.get("broker", "")).strip()
    if not broker:
        raise ValueError("Il mapping deve dichiarare un broker non vuoto.")
    columns_raw = _require_mapping(raw.get("columns"), "columns")
    unknown = set(columns_raw) - STANDARD_FIELDS
    if unknown:
        raise ValueError(f"Campi standard sconosciuti nel mapping: {sorted(unknown)}")
    columns = {str(k): str(v) for k, v in columns_raw.items()}
    required = {"data", "tipo", "id_operazione"}
    missing = required - set(columns)
    if missing:
        raise ValueError(f"Colonne obbligatorie non mappate: {sorted(missing)}")
    types = {
        str(k).strip().casefold(): str(v).strip().casefold()
        for k, v in _require_mapping(raw.get("operation_types", {}), "operation_types").items()
    }
    csv = _require_mapping(raw.get("csv", {}), "csv")
    decimal = _require_mapping(raw.get("decimal", {}), "decimal")
    excel = _require_mapping(raw.get("excel", {}), "excel")
    return BrokerMapping(
        broker=broker,
        columns=columns,
        operation_types=types,
        date_format=raw.get("date_format"),
        default_timezone=raw.get("default_timezone"),
        csv_separator=str(csv.get("separator", ",")),
        csv_encoding=str(csv.get("encoding", "utf-8-sig")),
        decimal_separator=str(decimal.get("separator", ".")),
        thousands_separator=(
            str(decimal["thousands_separator"])
            if decimal.get("thousands_separator") is not None
            else None
        ),
        excel_sheet=excel.get("sheet", 0),
    )

