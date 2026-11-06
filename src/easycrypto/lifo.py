"""Motore inventario LIFO globale per asset e cliente."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from .models import (
    DataIssue,
    DisposalResult,
    HoldingIncome,
    Lot,
    LotMatch,
    Operation,
    OperationType,
)


INCOME_TYPES = {OperationType.STAKING, OperationType.REWARD, OperationType.AIRDROP}


def _issue(op: Operation, code: str, message: str, asset: str) -> DataIssue:
    return DataIssue(code, message, op.broker, op.operation_id, op.source, asset)


def _latest_indices(lots: list[Lot], broker: str | None = None) -> list[int]:
    candidates = [
        index for index, lot in enumerate(lots) if lot.quantity > 0 and (broker is None or lot.current_broker == broker)
    ]
    return sorted(
        candidates,
        key=lambda index: (lots[index].acquired_at, lots[index].acquisition_id, index),
        reverse=True,
    )


def _consume(
    lots: list[Lot], quantity: Decimal, broker: str | None = None
) -> tuple[list[Lot], list[LotMatch]] | None:
    available = sum((lots[index].quantity for index in _latest_indices(lots, broker)), Decimal("0"))
    if available < quantity:
        return None
    remaining = quantity
    moved: list[Lot] = []
    matches: list[LotMatch] = []
    for index in _latest_indices(lots, broker):
        if remaining == 0:
            break
        lot = lots[index]
        used = min(lot.quantity, remaining)
        cost = used * lot.unit_cost_eur
        moved.append(replace(lot, quantity=used))
        matches.append(
            LotMatch(
                acquisition_id=lot.acquisition_id,
                acquisition_date=lot.acquired_at,
                acquisition_broker=lot.acquisition_broker,
                source=lot.source,
                quantity=used,
                cost_eur=cost,
            )
        )
        lot.quantity -= used
        remaining -= used
    lots[:] = [lot for lot in lots if lot.quantity > 0]
    return moved, matches


def calculate_asset_lifo(
    asset: str,
    operations: list[Operation],
    cutoff: datetime,
) -> tuple[list[DisposalResult], list[HoldingIncome], list[Lot], list[DataIssue]]:
    """Calcola un singolo asset; in caso di errore scarta ogni risultato dell'asset."""
    relevant = [op for op in operations if asset in op.assets() and op.date <= cutoff]
    relevant.sort(key=lambda op: (op.date, op.broker, op.operation_id))
    paired_destination = {
        op.transfer_id: op.broker
        for op in relevant
        if op.type is OperationType.DEPOSITO and op.transfer_id
    }
    lots: list[Lot] = []
    disposals: list[DisposalResult] = []
    income: list[HoldingIncome] = []

    for op in relevant:
        if op.type is OperationType.DEPOSITO:
            # Il lotto è già stato spostato dalla riga di prelievo abbinata.
            continue
        if op.type is OperationType.PRELIEVO and op.asset_out == asset:
            consumed = _consume(lots, op.quantity_out or Decimal("0"), op.broker)
            if consumed is None:
                return [], [], [], [_issue(op, "saldo_trasferimento", "Quantità insufficiente sul broker di origine per il trasferimento", asset)]
            moved, _ = consumed
            destination = paired_destination.get(op.transfer_id)
            if not destination:
                return [], [], [], [_issue(op, "destinazione_trasferimento", "Broker di destinazione non determinabile", asset)]
            for lot in moved:
                lot.current_broker = destination
                lots.append(lot)
            continue
        if op.type is OperationType.TRASFERIMENTO and op.asset_out == asset:
            consumed = _consume(lots, op.quantity_out or Decimal("0"), op.broker)
            if consumed is None:
                return [], [], [], [_issue(op, "saldo_trasferimento", "Quantità insufficiente sul broker di origine per il trasferimento", asset)]
            moved, _ = consumed
            for lot in moved:
                lot.current_broker = op.destination_broker or op.broker
                lots.append(lot)
            continue

        if op.asset_out == asset and op.type in {OperationType.VENDITA, OperationType.PERMUTA}:
            quantity = op.quantity_out or Decimal("0")
            consumed = _consume(lots, quantity)
            if consumed is None:
                return [], [], [], [_issue(op, "inventario_insufficiente", "Cessione superiore alla quantità disponibile; nessun lotto negativo creato", asset)]
            _, matches = consumed
            # Vendite e permute: la commissione riduce il corrispettivo.
            proceeds = (op.value_eur or Decimal("0")) - op.fee_eur
            if proceeds < 0:
                return [], [], [], [_issue(op, "corrispettivo_negativo", "La commissione supera il valore della cessione", asset)]
            cost = sum((match.cost_eur for match in matches), Decimal("0"))
            disposals.append(
                DisposalResult(
                    date=op.date,
                    asset=asset,
                    quantity=quantity,
                    proceeds_eur=proceeds,
                    cost_eur=cost,
                    gain_eur=proceeds - cost,
                    operation_id=op.operation_id,
                    broker=op.broker,
                    source=op.source,
                    group="pre-2025" if op.date.year < 2025 else "2025",
                    lot_matches=tuple(matches),
                )
            )

        if op.asset_in == asset and op.type in {
            OperationType.ACQUISTO,
            OperationType.PERMUTA,
            *INCOME_TYPES,
        }:
            quantity = op.quantity_in or Decimal("0")
            if quantity <= 0:
                return [], [], [], [
                    _issue(
                        op,
                        "quantita_acquisizione_non_positiva",
                        "La quantità acquisita deve essere maggiore di zero per calcolare il costo unitario",
                        asset,
                    )
                ]
            # Acquisto: la commissione aumenta il costo. Nella permuta è già attribuita alla cessione.
            cost = op.value_eur or Decimal("0")
            if op.type is OperationType.ACQUISTO:
                cost += op.fee_eur
            lots.append(
                Lot(
                    asset=asset,
                    quantity=quantity,
                    unit_cost_eur=cost / quantity,
                    acquired_at=op.date,
                    acquisition_id=op.operation_id,
                    acquisition_broker=op.broker,
                    current_broker=op.broker,
                    source=op.source,
                )
            )
            if op.type in INCOME_TYPES:
                # Provento tassato al ricevimento; lo stesso valore diventa costo del lotto.
                income.append(
                    HoldingIncome(
                        date=op.date,
                        asset=asset,
                        quantity=quantity,
                        taxable_eur=cost,
                        operation_id=op.operation_id,
                        broker=op.broker,
                        source=op.source,
                        type=op.type,
                    )
                )
    return disposals, income, lots, []

