"""Loader CSV/XLSX basato esclusivamente sui mapping YAML."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .mapping import BrokerMapping, load_broker_mapping
from .models import DataIssue, Operation
from .normalization import normalize_row


DEFAULT_MAX_ROWS = 500_000
DEFAULT_MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024


def _validate_limit(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} deve essere un intero positivo")


def load_operations(
    data_path: str | Path,
    mapping: BrokerMapping | str | Path,
    *,
    max_rows: int = DEFAULT_MAX_ROWS,
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
) -> tuple[list[Operation], list[DataIssue]]:
    """Legge un export e restituisce operazioni normalizzate ed errori di riga."""
    path = Path(data_path)
    _validate_limit(max_rows, "max_rows")
    _validate_limit(max_file_size_bytes, "max_file_size_bytes")
    file_size = path.stat().st_size
    if file_size > max_file_size_bytes:
        raise ValueError(
            f"File troppo grande: {file_size} byte; limite configurato "
            f"{max_file_size_bytes} byte ({path})"
        )
    config = load_broker_mapping(mapping) if not isinstance(mapping, BrokerMapping) else mapping
    suffix = path.suffix.casefold()
    sheet_name: str | None = None
    if suffix == ".csv":
        frame = pd.read_csv(
            path,
            sep=config.csv_separator,
            encoding=config.csv_encoding,
            dtype=str,
            keep_default_na=False,
            # Una riga sentinella permette di rilevare il superamento senza caricare tutto.
            nrows=max_rows + 1,
        )
    elif suffix in {".xlsx", ".xlsm"}:
        frame = pd.read_excel(
            path,
            sheet_name=config.excel_sheet,
            dtype=object,
            engine="openpyxl",
            nrows=max_rows + 1,
        )
        sheet_name = str(config.excel_sheet)
    else:
        raise ValueError(f"Formato file non supportato: {path.suffix}")

    if len(frame.index) > max_rows:
        raise ValueError(
            f"Troppe righe nel file: oltre {max_rows}; ridurre l'export o "
            "aumentare esplicitamente max_rows"
        )

    missing_columns = sorted(set(config.columns.values()) - set(frame.columns))
    if missing_columns:
        raise ValueError(f"Colonne sorgente mancanti: {missing_columns}")

    operations: list[Operation] = []
    issues: list[DataIssue] = []
    for index, series in frame.iterrows():
        # Riga 1 è l'intestazione sia in CSV sia nel foglio Excel.
        operation, issue = normalize_row(
            series.to_dict(), config, path.resolve(), int(index) + 2, sheet_name
        )
        if operation:
            operations.append(operation)
        if issue:
            issues.append(issue)
    return operations, issues

