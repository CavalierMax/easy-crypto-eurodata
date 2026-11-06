"""Prospetto RW e calcolo IVCA al 31 dicembre."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .models import Lot, RWLine, YearEndValuation
from .rt import money


def calculate_rw(
    lots: list[Lot], valuations: list[YearEndValuation], tax_year: int
) -> list[RWLine]:
    by_position: dict[tuple[str, str], list[Lot]] = defaultdict(list)
    for lot in lots:
        if lot.quantity > 0:
            by_position[(lot.asset, lot.current_broker)].append(lot)
    valuation_index = {
        (item.asset.upper(), item.broker): item
        for item in valuations
        if item.year == tax_year
    }
    lines: list[RWLine] = []
    for (asset, broker), position_lots in sorted(by_position.items()):
        quantity = sum((lot.quantity for lot in position_lots), Decimal("0"))
        valuation = valuation_index.get((asset, broker))
        if valuation and valuation.total_value_eur is not None:
            value = valuation.total_value_eur
            method = "valore_totale_piattaforma"
        elif valuation and valuation.unit_value_eur is not None:
            value = quantity * valuation.unit_value_eur
            method = "valore_unitario_piattaforma"
        else:
            value = sum((lot.cost_eur for lot in position_lots), Decimal("0"))
            method = "costo_acquisto"
        lines.append(
            RWLine(
                asset=asset,
                broker=broker,
                quantity=quantity,
                year_end_value_eur=money(value),
                ivca_eur=money(value * Decimal("0.002")),
                valuation_method=method,
                lot_ids=tuple(lot.acquisition_id for lot in position_lots),
            )
        )
    return lines

