"""Orchestrazione del calcolo fiscale EasyCrypto."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from .lifo import calculate_asset_lifo
from .models import (
    DataIssue,
    ManualRTInputs,
    Operation,
    TaxCalculation,
    YearEndValuation,
)
from .rt import calculate_rt
from .rw import calculate_rw
from .validation import attach_separate_fees, validate_operations


def _assert_decimal_inputs(
    operations: list[Operation], manual: ManualRTInputs, valuations: list[YearEndValuation]
) -> None:
    values: list[tuple[str, object]] = [
        ("RT43", manual.rt43),
        ("RT44 col. 2", manual.rt44_col2),
        ("RT45", manual.rt45),
    ]
    for op in operations:
        values.extend(
            (
                (f"{op.operation_id}.quantita_out", op.quantity_out),
                (f"{op.operation_id}.quantita_in", op.quantity_in),
                (f"{op.operation_id}.valore_eur", op.value_eur),
                (f"{op.operation_id}.commissione_eur", op.fee_eur),
            )
        )
    for item in valuations:
        values.extend(
            (
                (f"valutazione {item.asset}/{item.broker}.unitaria", item.unit_value_eur),
                (f"valutazione {item.asset}/{item.broker}.totale", item.total_value_eur),
            )
        )
    for name, value in values:
        if value is not None and not isinstance(value, Decimal):
            raise TypeError(f"{name} deve essere Decimal; ricevuto {type(value).__name__}")
    for name, value in (("RT43", manual.rt43), ("RT44 col. 2", manual.rt44_col2), ("RT45", manual.rt45)):
        if value < 0:
            raise ValueError(f"{name} non può essere negativo")
    for item in valuations:
        if item.year != 2025:
            continue
        if (item.unit_value_eur is None) == (item.total_value_eur is None):
            raise ValueError(
                f"La valutazione {item.asset}/{item.broker} deve indicare esattamente "
                "uno tra unit_value_eur e total_value_eur"
            )
        selected = item.unit_value_eur if item.unit_value_eur is not None else item.total_value_eur
        if selected is not None and selected < 0:
            raise ValueError(f"La valutazione {item.asset}/{item.broker} non può essere negativa")


def calculate_tax(
    operations: list[Operation],
    *,
    tax_year: int = 2025,
    manual_rt: ManualRTInputs | None = None,
    year_end_valuations: list[YearEndValuation] | None = None,
    initial_errors: list[DataIssue] | None = None,
) -> TaxCalculation:
    """Calcola plusvalenze, righi RT e prospetto RW per il solo anno 2025."""
    if tax_year != 2025:
        raise ValueError(
            "EasyCrypto implementa esclusivamente il periodo d'imposta 2025; "
            "l'aliquota 33% dal 2026 non è implementata."
        )
    manual = manual_rt or ManualRTInputs()
    valuations = year_end_valuations or []
    _assert_decimal_inputs(operations, manual, valuations)
    ordered = sorted(operations, key=lambda op: (op.date, op.broker, op.operation_id))
    without_fee_rows, fee_issues = attach_separate_fees(ordered)
    errors = list(initial_errors or []) + fee_issues + validate_operations(ordered)
    cutoff = datetime(tax_year, 12, 31, 23, 59, 59, 999999, tzinfo=UTC)
    warnings: list[DataIssue] = []
    for op in without_fee_rows:
        if op.date > cutoff:
            warnings.append(
                DataIssue(
                    code="operazione_futura",
                    message=f"Operazione successiva al {tax_year} ignorata",
                    broker=op.broker,
                    operation_id=op.operation_id,
                    source=op.source,
                    asset=op.asset_out or op.asset_in,
                    severity="avvertenza",
                )
            )

    blocked_assets = {issue.asset for issue in errors if issue.asset}
    # Se l'errore è legato a una riga nota, blocca tutti gli asset della riga (es. permuta).
    for issue in errors:
        for op in ordered:
            if op.broker == issue.broker and op.operation_id == issue.operation_id:
                blocked_assets.update(op.assets())
                if op.type.value == "commissione" and op.linked_operation_id:
                    for target in ordered:
                        if target.broker == op.broker and target.operation_id == op.linked_operation_id:
                            blocked_assets.update(target.assets())
    assets = sorted({asset for op in without_fee_rows for asset in op.assets()})
    all_disposals = []
    all_income = []
    all_lots = []
    for asset in assets:
        if asset in blocked_assets:
            continue
        disposals, income, lots, runtime_errors = calculate_asset_lifo(
            asset, without_fee_rows, cutoff
        )
        if runtime_errors:
            errors.extend(runtime_errors)
            blocked_assets.add(asset)
            continue
        all_disposals.extend(disposals)
        all_income.extend(income)
        all_lots.extend(lots)

    all_disposals.sort(key=lambda item: (item.date, item.broker, item.operation_id, item.asset))
    all_income.sort(key=lambda item: (item.date, item.broker, item.operation_id, item.asset))
    rw = calculate_rw(all_lots, valuations, tax_year)
    valuation_keys = {(item.asset.upper(), item.broker) for item in valuations if item.year == tax_year}
    for line in rw:
        if (line.asset, line.broker) not in valuation_keys:
            lot = next(lot for lot in all_lots if lot.asset == line.asset and lot.current_broker == line.broker)
            warnings.append(
                DataIssue(
                    code="rw_costo_fallback",
                    message="Valore di piattaforma al 31 dicembre assente: usato il costo di acquisto",
                    broker=line.broker,
                    operation_id=lot.acquisition_id,
                    source=lot.source,
                    asset=line.asset,
                    severity="avvertenza",
                )
            )
    return TaxCalculation(
        tax_year=tax_year,
        disposals=tuple(all_disposals),
        holding_income=tuple(all_income),
        rt=calculate_rt(all_disposals, manual),
        rw=tuple(rw),
        errors=tuple(errors),
        warnings=tuple(warnings),
        incomplete=bool(errors),
    )

