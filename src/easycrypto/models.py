"""Modelli immutabili e tracciabili usati dal motore fiscale."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path


ZERO = Decimal("0")


class OperationType(StrEnum):
    ACQUISTO = "acquisto"
    VENDITA = "vendita"
    PERMUTA = "permuta"
    STAKING = "staking"
    REWARD = "reward"
    AIRDROP = "airdrop"
    DEPOSITO = "deposito"
    PRELIEVO = "prelievo"
    TRASFERIMENTO = "trasferimento"
    COMMISSIONE = "commissione"


@dataclass(frozen=True, slots=True)
class SourceRef:
    file: Path
    row: int
    sheet: str | None = None

    def display(self) -> str:
        sheet = f", foglio {self.sheet}" if self.sheet else ""
        return f"{self.file}, riga {self.row}{sheet}"


@dataclass(frozen=True, slots=True)
class Operation:
    date: datetime
    broker: str
    type: OperationType
    asset_out: str | None
    quantity_out: Decimal | None
    asset_in: str | None
    quantity_in: Decimal | None
    value_eur: Decimal | None
    fee_eur: Decimal
    operation_id: str
    source: SourceRef
    transfer_id: str | None = None
    destination_broker: str | None = None
    linked_operation_id: str | None = None

    def assets(self) -> frozenset[str]:
        return frozenset(a for a in (self.asset_out, self.asset_in) if a)


@dataclass(frozen=True, slots=True)
class DataIssue:
    code: str
    message: str
    broker: str
    operation_id: str
    source: SourceRef
    asset: str | None = None
    severity: str = "errore"

    def __str__(self) -> str:
        return (
            f"{self.message} [{self.source.display()}; broker={self.broker}; "
            f"id_operazione={self.operation_id}]"
        )


@dataclass(slots=True)
class Lot:
    asset: str
    quantity: Decimal
    unit_cost_eur: Decimal
    acquired_at: datetime
    acquisition_id: str
    acquisition_broker: str
    current_broker: str
    source: SourceRef

    @property
    def cost_eur(self) -> Decimal:
        return self.quantity * self.unit_cost_eur


@dataclass(frozen=True, slots=True)
class LotMatch:
    acquisition_id: str
    acquisition_date: datetime
    acquisition_broker: str
    source: SourceRef
    quantity: Decimal
    cost_eur: Decimal


@dataclass(frozen=True, slots=True)
class DisposalResult:
    date: datetime
    asset: str
    quantity: Decimal
    proceeds_eur: Decimal
    cost_eur: Decimal
    gain_eur: Decimal
    operation_id: str
    broker: str
    source: SourceRef
    group: str
    lot_matches: tuple[LotMatch, ...]


@dataclass(frozen=True, slots=True)
class HoldingIncome:
    date: datetime
    asset: str
    quantity: Decimal
    taxable_eur: Decimal
    operation_id: str
    broker: str
    source: SourceRef
    type: OperationType


@dataclass(frozen=True, slots=True)
class ManualRTInputs:
    rt43: Decimal = ZERO
    rt44_col2: Decimal = ZERO
    rt45: Decimal = ZERO
    rt43_reference: str | None = None
    rt44_reference: str | None = None
    rt45_reference: str | None = None


@dataclass(frozen=True, slots=True)
class RTLines:
    rt41_col1: Decimal
    rt41_col2: Decimal
    rt41_col3: Decimal
    rt41_col4: Decimal
    rt57_col2: Decimal
    rt88: Decimal
    rt89: Decimal
    rt90: Decimal
    minus_2025_carryforward: Decimal
    carryforward_expires_after: int | None
    pre_2025_net_by_year: dict[int, Decimal]
    operation_ids_by_line: dict[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class YearEndValuation:
    year: int
    broker: str
    asset: str
    unit_value_eur: Decimal | None = None
    total_value_eur: Decimal | None = None
    source_description: str | None = None


@dataclass(frozen=True, slots=True)
class RWLine:
    asset: str
    broker: str
    quantity: Decimal
    year_end_value_eur: Decimal
    ivca_eur: Decimal
    valuation_method: str
    lot_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TaxCalculation:
    tax_year: int
    disposals: tuple[DisposalResult, ...]
    holding_income: tuple[HoldingIncome, ...]
    rt: RTLines | None
    rw: tuple[RWLine, ...]
    errors: tuple[DataIssue, ...] = field(default_factory=tuple)
    warnings: tuple[DataIssue, ...] = field(default_factory=tuple)
    incomplete: bool = False

