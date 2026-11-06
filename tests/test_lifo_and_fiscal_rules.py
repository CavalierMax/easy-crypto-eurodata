from decimal import Decimal
from datetime import UTC, datetime

from easycrypto import calculate_tax
from easycrypto.lifo import calculate_asset_lifo


def test_global_lifo_is_sorted_and_spans_brokers(make_operation):
    """A mano: vendita 1,5; LIFO usa 1x2000 + 0,5x1000 = costo 2500."""
    old = make_operation("2024-01-01T10:00:00Z", "BUY-OLD", "acquisto", asset_in="BTC", quantity_in="1", value="1000")
    recent = make_operation("2025-01-01T10:00:00Z", "BUY-NEW", "acquisto", broker="BrokerB", asset_in="BTC", quantity_in="1", value="2000")
    sale = make_operation("2025-06-01T10:00:00Z", "SELL", "vendita", asset_out="BTC", quantity_out="1.5", value="4500", fee="100")
    result = calculate_tax([sale, old, recent])
    disposal = result.disposals[0]
    assert disposal.proceeds_eur == Decimal("4400")
    assert disposal.cost_eur == Decimal("2500.0")
    assert disposal.gain_eur == Decimal("1900.0")
    assert [match.acquisition_id for match in disposal.lot_matches] == ["BUY-NEW", "BUY-OLD"]
    assert result.rt.rt41_col3 == Decimal("4400.00")
    assert result.rt.rt41_col4 == Decimal("2500.00")


def test_purchase_fee_increases_lot_cost(make_operation):
    """A mano: acquisto 100 + commissione 5; vendita 150 => plusvalenza 45."""
    buy = make_operation("2025-01-01T00:00:00Z", "B", "acquisto", asset_in="ETH", quantity_in="1", value="100", fee="5")
    sale = make_operation("2025-02-01T00:00:00Z", "S", "vendita", asset_out="ETH", quantity_out="1", value="150")
    result = calculate_tax([buy, sale])
    assert result.disposals[0].cost_eur == Decimal("105")
    assert result.disposals[0].gain_eur == Decimal("45")


def test_swap_is_disposal_and_creates_new_lot(make_operation):
    """A mano: BTC costo 100, permuta 300 con fee 10 => gain 190; ETH costa 300."""
    buy = make_operation("2025-01-01T00:00:00Z", "B", "acquisto", asset_in="BTC", quantity_in="1", value="100")
    swap = make_operation("2025-02-01T00:00:00Z", "P", "permuta", asset_out="BTC", quantity_out="1", asset_in="ETH", quantity_in="10", value="300", fee="10")
    result = calculate_tax([buy, swap])
    assert result.disposals[0].proceeds_eur == Decimal("290")
    assert result.disposals[0].gain_eur == Decimal("190")
    assert next(line for line in result.rw if line.asset == "ETH").year_end_value_eur == Decimal("300.00")


def test_holding_income_is_taxed_at_receipt_and_becomes_cost(make_operation):
    """A mano: reward tassato 100; successiva vendita 150 genera gain 50, non 150."""
    reward = make_operation("2025-01-01T00:00:00Z", "R", "reward", asset_in="SOL", quantity_in="2", value="100")
    sale = make_operation("2025-03-01T00:00:00Z", "S", "vendita", asset_out="SOL", quantity_out="2", value="150")
    result = calculate_tax([reward, sale])
    assert result.holding_income[0].taxable_eur == Decimal("100")
    assert result.disposals[0].cost_eur == Decimal("100")
    assert result.disposals[0].gain_eur == Decimal("50")


def test_transfer_preserves_original_lot_and_changes_rw_broker(make_operation):
    """A mano: 2 token costano 200; 1 trasferito conserva costo unitario 100."""
    buy = make_operation("2025-01-01T00:00:00Z", "B", "acquisto", asset_in="ADA", quantity_in="2", value="200")
    withdrawal = make_operation("2025-02-01T00:00:00Z", "W", "prelievo", asset_out="ADA", quantity_out="1", transfer_id="T1")
    deposit = make_operation("2025-02-01T01:00:00Z", "D", "deposito", broker="BrokerB", asset_in="ADA", quantity_in="1", transfer_id="T1")
    result = calculate_tax([deposit, withdrawal, buy])
    assert not result.errors
    assert {(line.broker, line.quantity, line.year_end_value_eur) for line in result.rw} == {
        ("BrokerA", Decimal("1"), Decimal("100.00")),
        ("BrokerB", Decimal("1"), Decimal("100.00")),
    }
    assert not result.disposals


def test_separate_fee_row_is_attached_to_sale(make_operation):
    """A mano: vendita 200 - fee separata 10 - costo 100 = gain 90."""
    buy = make_operation("2025-01-01T00:00:00Z", "B", "acquisto", asset_in="XRP", quantity_in="1", value="100")
    sale = make_operation("2025-02-01T00:00:00Z", "S", "vendita", asset_out="XRP", quantity_out="1", value="200")
    fee = make_operation("2025-02-01T00:00:01Z", "F", "commissione", fee="10", linked_operation_id="S")
    assert calculate_tax([buy, sale, fee]).disposals[0].gain_eur == Decimal("90")


def test_lifo_rejects_zero_acquisition_without_upstream_validation(make_operation):
    """Il motore LIFO diretto restituisce un DataIssue, non ZeroDivisionError."""
    invalid = make_operation(
        "2025-01-01T00:00:00Z",
        "ZERO",
        "acquisto",
        asset_in="BTC",
        quantity_in="0",
        value="100",
    )
    disposals, income, lots, errors = calculate_asset_lifo(
        "BTC",
        [invalid],
        datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC),
    )
    assert not disposals and not income and not lots
    assert errors[0].code == "quantita_acquisizione_non_positiva"
    assert errors[0].operation_id == "ZERO"


