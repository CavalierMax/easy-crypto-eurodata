from decimal import Decimal

import pytest

from easycrypto import ManualRTInputs, calculate_tax


def test_missing_value_blocks_only_affected_asset(make_operation):
    bad = make_operation("2025-01-01T00:00:00Z", "BAD", "acquisto", asset_in="BTC", quantity_in="1")
    good = make_operation("2025-01-01T00:00:00Z", "GOOD", "acquisto", asset_in="ETH", quantity_in="1", value="100")
    result = calculate_tax([bad, good])
    assert result.incomplete
    assert result.errors[0].source.row > 0
    assert result.errors[0].broker == "BrokerA"
    assert result.errors[0].operation_id == "BAD"
    assert {line.asset for line in result.rw} == {"ETH"}


def test_insufficient_inventory_never_creates_negative_lot(make_operation):
    sale = make_operation("2025-01-01T00:00:00Z", "S", "vendita", asset_out="BTC", quantity_out="1", value="100")
    result = calculate_tax([sale])
    assert result.incomplete
    assert result.errors[0].code == "inventario_insufficiente"
    assert not result.disposals
    assert not result.rw


def test_negative_values_are_not_silently_fixed(make_operation):
    operation = make_operation("2025-01-01T00:00:00Z", "B", "acquisto", asset_in="BTC", quantity_in="-1", value="-100", fee="-2")
    result = calculate_tax([operation])
    assert {issue.code for issue in result.errors} >= {"quantita_non_positiva", "valore_negativo", "commissione_negativa"}


def test_duplicate_broker_operation_id_is_an_error(make_operation):
    first = make_operation("2025-01-01T00:00:00Z", "DUP", "acquisto", asset_in="BTC", quantity_in="1", value="100")
    second = make_operation("2025-01-02T00:00:00Z", "DUP", "acquisto", asset_in="ETH", quantity_in="1", value="100")
    result = calculate_tax([first, second])
    assert result.incomplete
    assert all(issue.code == "id_duplicato" for issue in result.errors)


def test_float_monetary_input_is_rejected():
    with pytest.raises(TypeError, match="Decimal"):
        calculate_tax([], manual_rt=ManualRTInputs(rt43=1.5))  # type: ignore[arg-type]

