from decimal import Decimal

import pandas as pd
import pytest

from easycrypto import calculate_tax
from easycrypto.loader import load_operations
from easycrypto.mapping import load_broker_mapping


def test_csv_loader_uses_yaml_decimal_and_timezone(tmp_path):
    mapping = tmp_path / "broker.yaml"
    mapping.write_text(
        '''broker: TestBroker
columns:
  data: Data
  tipo: Tipo
  asset_in: Asset
  quantita_in: Quantita
  valore_eur: Valore
  commissione_eur: Fee
  id_operazione: ID
operation_types:
  compra: acquisto
date_format: "%d/%m/%Y %H:%M"
default_timezone: Europe/Rome
csv:
  separator: ";"
decimal:
  separator: ","
  thousands_separator: "."
''', encoding="utf-8")
    data = tmp_path / "input.csv"
    data.write_text(
        "Data;Tipo;Asset;Quantita;Valore;Fee;ID\n01/01/2025 10:00;compra;BTC;1,5;1.234,56;5,44;A1\n",
        encoding="utf-8-sig",
    )
    operations, errors = load_operations(data, mapping)
    assert not errors
    assert operations[0].quantity_in == Decimal("1.5")
    assert operations[0].value_eur == Decimal("1234.56")
    assert operations[0].date.isoformat() == "2025-01-01T09:00:00+00:00"
    assert operations[0].source.row == 2


def test_xlsx_loader_preserves_source_row(tmp_path):
    mapping = tmp_path / "broker.yaml"
    mapping.write_text(
        '''broker: TestBroker
columns:
  data: Date
  tipo: Type
  asset_in: Asset
  quantita_in: Quantity
  valore_eur: Value
  id_operazione: ID
operation_types: {}
default_timezone: UTC
excel:
  sheet: 0
''', encoding="utf-8")
    data = tmp_path / "input.xlsx"
    pd.DataFrame([{"Date": "2025-01-01T00:00:00+00:00", "Type": "acquisto", "Asset": "BTC", "Quantity": "1", "Value": "100", "ID": "A1"}]).to_excel(data, index=False)
    operations, errors = load_operations(data, load_broker_mapping(mapping))
    assert not errors
    assert operations[0].source.row == 2
    assert operations[0].source.sheet == "0"


def test_naive_date_without_configured_timezone_is_row_error(tmp_path):
    mapping = tmp_path / "broker.yaml"
    mapping.write_text(
        '''broker: TestBroker
columns:
  data: Date
  tipo: Type
  asset_in: Asset
  quantita_in: Quantity
  valore_eur: Value
  id_operazione: ID
operation_types: {}
''', encoding="utf-8")
    data = tmp_path / "input.csv"
    data.write_text("Date,Type,Asset,Quantity,Value,ID\n2025-01-01 10:00:00,acquisto,BTC,1,100,A1\n", encoding="utf-8-sig")
    operations, errors = load_operations(data, mapping)
    assert not operations
    assert "fuso orario" in errors[0].message


def test_broker_names_are_canonical_across_rows_and_destination(tmp_path):
    mapping = tmp_path / "broker.yaml"
    mapping.write_text(
        '''broker: Kraken
columns:
  data: Date
  broker: Broker
  tipo: Type
  asset_out: AssetOut
  quantita_out: QuantityOut
  asset_in: AssetIn
  quantita_in: QuantityIn
  valore_eur: Value
  id_operazione: ID
  broker_destinazione: Destination
operation_types: {}
default_timezone: UTC
''', encoding="utf-8")
    data = tmp_path / "brokers.csv"
    data.write_text(
        "Date,Broker,Type,AssetOut,QuantityOut,AssetIn,QuantityIn,Value,ID,Destination\n"
        "2025-01-01T00:00:00Z,Kraken,acquisto,,,BTC,1,100,B1,\n"
        "2025-01-02T00:00:00Z,KRAKEN,acquisto,,,BTC,1,100,B2,\n"
        "2025-02-01T00:00:00Z,KRAKEN,trasferimento,BTC,1,BTC,1,,T1,  LEDGER  \n",
        encoding="utf-8-sig",
    )
    operations, errors = load_operations(data, mapping)
    assert not errors
    assert {operation.broker for operation in operations} == {"kraken"}
    assert operations[-1].destination_broker == "ledger"

    result = calculate_tax(operations)
    assert not result.errors
    assert {(line.broker, line.quantity) for line in result.rw} == {
        ("kraken", Decimal("1")),
        ("ledger", Decimal("1")),
    }


@pytest.mark.parametrize("extension", ["csv", "xlsx"])
def test_loader_stops_when_row_limit_is_exceeded(tmp_path, extension):
    mapping = tmp_path / "broker.yaml"
    mapping.write_text(
        f'''broker: TestBroker
columns:
  data: Date
  tipo: Type
  asset_in: Asset
  quantita_in: Quantity
  valore_eur: Value
  id_operazione: ID
operation_types: {{}}
default_timezone: UTC
excel:
  sheet: 0
''', encoding="utf-8")
    rows = [
        {"Date": "2025-01-01T00:00:00Z", "Type": "acquisto", "Asset": "BTC", "Quantity": "1", "Value": "100", "ID": "A1"},
        {"Date": "2025-01-02T00:00:00Z", "Type": "acquisto", "Asset": "ETH", "Quantity": "1", "Value": "100", "ID": "A2"},
    ]
    data = tmp_path / f"input.{extension}"
    if extension == "csv":
        pd.DataFrame(rows).to_csv(data, index=False)
    else:
        pd.DataFrame(rows).to_excel(data, index=False)

    with pytest.raises(ValueError, match="Troppe righe.*oltre 1"):
        load_operations(data, mapping, max_rows=1)


def test_loader_rejects_file_size_before_parsing(tmp_path):
    mapping = tmp_path / "broker.yaml"
    mapping.write_text(
        '''broker: TestBroker
columns:
  data: Date
  tipo: Type
  id_operazione: ID
operation_types: {}
''', encoding="utf-8")
    data = tmp_path / "large.csv"
    data.write_text("Date,Type,ID\n2025-01-01,acquisto,A1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="File troppo grande"):
        load_operations(data, mapping, max_file_size_bytes=10)

