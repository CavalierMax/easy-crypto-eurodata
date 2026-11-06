"""Validazione semantica delle operazioni prima del calcolo."""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal

from .models import DataIssue, Operation, OperationType


VALUED_TYPES = {
    OperationType.ACQUISTO,
    OperationType.VENDITA,
    OperationType.PERMUTA,
    OperationType.STAKING,
    OperationType.REWARD,
    OperationType.AIRDROP,
}
INCOME_TYPES = {OperationType.STAKING, OperationType.REWARD, OperationType.AIRDROP}


def _issue(op: Operation, code: str, message: str, asset: str | None = None) -> DataIssue:
    return DataIssue(code, message, op.broker, op.operation_id, op.source, asset)


def validate_operations(operations: list[Operation]) -> list[DataIssue]:
    """Restituisce tutti gli errori rilevabili senza modificare i dati."""
    issues: list[DataIssue] = []
    identifiers = Counter((op.broker, op.operation_id) for op in operations)
    transfer_groups: dict[str, list[Operation]] = defaultdict(list)

    for op in operations:
        asset = op.asset_out or op.asset_in
        if not op.operation_id or op.operation_id == "<mancante>":
            issues.append(_issue(op, "id_mancante", "id_operazione mancante", asset))
        elif identifiers[(op.broker, op.operation_id)] > 1:
            issues.append(
                _issue(op, "id_duplicato", "La coppia broker/id_operazione è duplicata", asset)
            )
        if op.fee_eur < 0:
            issues.append(_issue(op, "commissione_negativa", "commissione_eur non può essere negativa", asset))
        for name, quantity, quantity_asset in (
            ("quantita_out", op.quantity_out, op.asset_out),
            ("quantita_in", op.quantity_in, op.asset_in),
        ):
            if quantity is not None and quantity <= 0:
                issues.append(_issue(op, "quantita_non_positiva", f"{name} deve essere maggiore di zero", quantity_asset))
        if op.value_eur is not None and op.value_eur < 0:
            issues.append(_issue(op, "valore_negativo", "valore_eur non può essere negativo", asset))
        if op.type in VALUED_TYPES and op.value_eur is None:
            issues.append(_issue(op, "valore_mancante", "valore_eur obbligatorio per questa operazione", asset))

        if op.type is OperationType.ACQUISTO:
            if not op.asset_in or op.quantity_in is None or op.asset_out or op.quantity_out is not None:
                issues.append(_issue(op, "forma_acquisto", "Un acquisto richiede solo asset_in e quantita_in", asset))
        elif op.type is OperationType.VENDITA:
            if not op.asset_out or op.quantity_out is None or op.asset_in or op.quantity_in is not None:
                issues.append(_issue(op, "forma_vendita", "Una vendita richiede solo asset_out e quantita_out", asset))
        elif op.type is OperationType.PERMUTA:
            if not op.asset_out or op.quantity_out is None or not op.asset_in or op.quantity_in is None:
                issues.append(_issue(op, "forma_permuta", "Una permuta richiede asset e quantità sia in uscita sia in entrata", asset))
            elif op.asset_out == op.asset_in:
                issues.append(_issue(op, "permuta_stesso_asset", "Una permuta deve coinvolgere asset diversi", asset))
        elif op.type in INCOME_TYPES:
            if not op.asset_in or op.quantity_in is None or op.asset_out or op.quantity_out is not None:
                issues.append(_issue(op, "forma_provento", "Il provento richiede solo asset_in e quantita_in", asset))
        elif op.type is OperationType.PRELIEVO:
            if not op.asset_out or op.quantity_out is None or not op.transfer_id:
                issues.append(_issue(op, "forma_prelievo", "Il prelievo richiede asset_out, quantita_out e id_trasferimento", asset))
        elif op.type is OperationType.DEPOSITO:
            if not op.asset_in or op.quantity_in is None or not op.transfer_id:
                issues.append(_issue(op, "forma_deposito", "Il deposito richiede asset_in, quantita_in e id_trasferimento", asset))
        elif op.type is OperationType.TRASFERIMENTO:
            if (
                not op.asset_out
                or op.quantity_out is None
                or op.asset_in != op.asset_out
                or op.quantity_in != op.quantity_out
                or not op.destination_broker
            ):
                issues.append(_issue(op, "forma_trasferimento", "Il trasferimento richiede stesso asset/quantità in entrata e uscita e broker_destinazione", asset))
        elif op.type is OperationType.COMMISSIONE:
            if not op.linked_operation_id:
                issues.append(_issue(op, "commissione_non_collegata", "Una commissione separata richiede id_operazione_collegata", asset))
            if op.fee_eur <= Decimal("0"):
                issues.append(_issue(op, "commissione_vuota", "Una commissione separata richiede commissione_eur positiva", asset))

        if op.transfer_id:
            transfer_groups[op.transfer_id].append(op)

    for transfer_id, rows in transfer_groups.items():
        withdrawals = [op for op in rows if op.type is OperationType.PRELIEVO]
        deposits = [op for op in rows if op.type is OperationType.DEPOSITO]
        if len(withdrawals) != 1 or len(deposits) != 1:
            for op in rows:
                issues.append(_issue(op, "trasferimento_non_abbinato", f"id_trasferimento {transfer_id!r} deve avere un prelievo e un deposito", op.asset_out or op.asset_in))
            continue
        outgoing, incoming = withdrawals[0], deposits[0]
        if outgoing.asset_out != incoming.asset_in or outgoing.quantity_out != incoming.quantity_in:
            for op in rows:
                issues.append(_issue(op, "trasferimento_incoerente", f"Asset o quantità discordanti per id_trasferimento {transfer_id!r}", op.asset_out or op.asset_in))
    return issues


def attach_separate_fees(operations: list[Operation]) -> tuple[list[Operation], list[DataIssue]]:
    """Somma le righe commissione all'operazione collegata senza mutare gli input."""
    from dataclasses import replace

    targets = {(op.broker, op.operation_id): op for op in operations if op.type is not OperationType.COMMISSIONE}
    extra: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    issues: list[DataIssue] = []
    for fee in (op for op in operations if op.type is OperationType.COMMISSIONE):
        key = (fee.broker, fee.linked_operation_id or "")
        if key not in targets:
            issues.append(_issue(fee, "collegamento_commissione", "Operazione collegata alla commissione non trovata"))
        else:
            extra[key] += fee.fee_eur
    result = [
        replace(op, fee_eur=op.fee_eur + extra[(op.broker, op.operation_id)])
        for op in operations
        if op.type is not OperationType.COMMISSIONE
    ]
    return result, issues

