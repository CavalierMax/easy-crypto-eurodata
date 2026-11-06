"""Aggregazione dei righi RT richiesti per il periodo d'imposta 2025."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from .models import DisposalResult, ManualRTInputs, RTLines


CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_rt(
    disposals: list[DisposalResult], manual: ManualRTInputs
) -> RTLines:
    pre = [item for item in disposals if item.group == "pre-2025"]
    current = [item for item in disposals if item.group == "2025"]
    pre_by_year: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    ids_by_year: dict[int, list[str]] = defaultdict(list)
    for item in pre:
        pre_by_year[item.date.year] += item.gain_eur
        ids_by_year[item.date.year].append(item.operation_id)

    # Franchigia pre-2025: per ciascun anno, fino a 2.000 euro il risultato non confluisce in RT57.
    eligible_pre = sum(
        (amount for amount in pre_by_year.values() if amount > Decimal("2000")),
        Decimal("0"),
    )
    current_net = sum((item.gain_eur for item in current), Decimal("0"))
    rt57 = eligible_pre + current_net
    rt88 = rt57 - manual.rt43 - manual.rt44_col2
    rt89 = rt88 * Decimal("0.26")
    rt90 = rt89 - manual.rt45
    pre_ids = tuple(item.operation_id for item in pre)
    current_ids = tuple(item.operation_id for item in current)
    return RTLines(
        rt41_col1=money(sum((item.proceeds_eur for item in pre), Decimal("0"))),
        rt41_col2=money(sum((item.cost_eur for item in pre), Decimal("0"))),
        rt41_col3=money(sum((item.proceeds_eur for item in current), Decimal("0"))),
        rt41_col4=money(sum((item.cost_eur for item in current), Decimal("0"))),
        rt57_col2=money(rt57),
        rt88=money(rt88),
        rt89=money(rt89),
        rt90=money(rt90),
        # La minusvalenza netta 2025 è esposta per i quattro periodi successivi.
        minus_2025_carryforward=money(max(-current_net, Decimal("0"))),
        carryforward_expires_after=2029 if current_net < 0 else None,
        pre_2025_net_by_year={year: money(value) for year, value in sorted(pre_by_year.items())},
        operation_ids_by_line={
            "RT41_col1": pre_ids,
            "RT41_col2": pre_ids,
            "RT41_col3": current_ids,
            "RT41_col4": current_ids,
            "RT57_col2": tuple(
                item.operation_id
                for item in disposals
                if item.group == "2025"
                or (item.date.year in pre_by_year and pre_by_year[item.date.year] > Decimal("2000"))
            ),
            "RT88": tuple(item.operation_id for item in disposals),
            "RT89": tuple(item.operation_id for item in disposals),
            "RT90": tuple(item.operation_id for item in disposals),
        },
    )

