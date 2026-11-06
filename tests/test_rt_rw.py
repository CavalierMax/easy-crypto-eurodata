from decimal import Decimal

from easycrypto import ManualRTInputs, YearEndValuation, calculate_tax


def _round_trip(make_operation, asset, year, cost, proceeds):
    return [
        make_operation(f"{year}-01-01T00:00:00Z", f"{asset}-B", "acquisto", asset_in=asset, quantity_in="1", value=str(cost)),
        make_operation(f"{year}-06-01T00:00:00Z", f"{asset}-S", "vendita", asset_out=asset, quantity_out="1", value=str(proceeds)),
    ]


def test_pre_2025_threshold_is_annual_and_current_year_has_none(make_operation):
    """2023 gain 1500 escluso; 2024 gain 2500 incluso; 2025 loss 100 => RT57 2400."""
    operations = []
    operations += _round_trip(make_operation, "A23", 2023, 1000, 2500)
    operations += _round_trip(make_operation, "A24", 2024, 1000, 3500)
    operations += _round_trip(make_operation, "A25", 2025, 1000, 900)
    result = calculate_tax(operations)
    assert result.rt.pre_2025_net_by_year == {2023: Decimal("1500.00"), 2024: Decimal("2500.00")}
    assert result.rt.rt57_col2 == Decimal("2400.00")
    assert result.rt.minus_2025_carryforward == Decimal("100.00")
    assert result.rt.carryforward_expires_after == 2029


def test_manual_rt_inputs_and_rate_are_applied_literally(make_operation):
    """RT57 2400 - 100 - 200 = 2100; 26%=546; meno RT45 50 = 496."""
    result = calculate_tax(
        _round_trip(make_operation, "BTC", 2025, 100, 2500),
        manual_rt=ManualRTInputs(rt43=Decimal("100"), rt44_col2=Decimal("200"), rt45=Decimal("50")),
    )
    assert result.rt.rt57_col2 == Decimal("2400.00")
    assert result.rt.rt88 == Decimal("2100.00")
    assert result.rt.rt89 == Decimal("546.00")
    assert result.rt.rt90 == Decimal("496.00")
    assert result.rt.operation_ids_by_line["RT41_col3"] == ("BTC-S",)


def test_rw_platform_value_and_ivca(make_operation):
    """2 token x 300 euro = 600 euro; IVCA 0,20% = 1,20 euro."""
    buy = make_operation("2025-01-01T00:00:00Z", "B", "acquisto", asset_in="ETH", quantity_in="2", value="200")
    result = calculate_tax([buy], year_end_valuations=[YearEndValuation(2025, "BrokerA", "ETH", unit_value_eur=Decimal("300"))])
    line = result.rw[0]
    assert line.year_end_value_eur == Decimal("600.00")
    assert line.ivca_eur == Decimal("1.20")
    assert line.valuation_method == "valore_unitario_piattaforma"


def test_rw_falls_back_to_residual_cost_with_warning(make_operation):
    buy = make_operation("2025-01-01T00:00:00Z", "B", "acquisto", asset_in="BTC", quantity_in="2", value="1000")
    result = calculate_tax([buy])
    assert result.rw[0].year_end_value_eur == Decimal("1000.00")
    assert result.rw[0].ivca_eur == Decimal("2.00")
    assert result.warnings[0].code == "rw_costo_fallback"


def test_non_2025_period_is_explicitly_rejected():
    try:
        calculate_tax([], tax_year=2026)
    except ValueError as error:
        assert "33%" in str(error)
    else:
        raise AssertionError("Il periodo 2026 doveva essere rifiutato")

