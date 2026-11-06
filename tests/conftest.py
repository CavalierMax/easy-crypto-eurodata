from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from easycrypto.models import Operation, OperationType, SourceRef


@pytest.fixture
def make_operation():
    counter = 0

    def factory(date: str, operation_id: str, operation_type: str, *, broker: str = "BrokerA", asset_out: str | None = None, quantity_out: str | None = None, asset_in: str | None = None, quantity_in: str | None = None, value: str | None = None, fee: str = "0", transfer_id: str | None = None, destination_broker: str | None = None, linked_operation_id: str | None = None) -> Operation:
        nonlocal counter
        counter += 1
        return Operation(
            date=datetime.fromisoformat(date.replace("Z", "+00:00")).astimezone(UTC),
            broker=broker,
            type=OperationType(operation_type),
            asset_out=asset_out,
            quantity_out=Decimal(quantity_out) if quantity_out is not None else None,
            asset_in=asset_in,
            quantity_in=Decimal(quantity_in) if quantity_in is not None else None,
            value_eur=Decimal(value) if value is not None else None,
            fee_eur=Decimal(fee),
            operation_id=operation_id,
            source=SourceRef(Path("input.csv"), counter + 1),
            transfer_id=transfer_id,
            destination_broker=destination_broker,
            linked_operation_id=linked_operation_id,
        )
    return factory

