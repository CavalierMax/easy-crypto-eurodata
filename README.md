# EasyCrypto Tax Engine

Motore Python 3.12 per preparare dati fiscalmente tracciabili relativi alle
cripto-attività del periodo d'imposta 2025. Produce strutture dati; non genera
Excel o PDF.

> ⚠️ **Avvertenza importante**: questo software è uno strumento di calcolo di
> supporto, non un consulente fiscale. Prima di usare uno qualsiasi dei
> risultati (righi RT, prospetto RW, importi) per compilare un dichiarativo,
> l'utente deve **sempre controllare manualmente** i dati prodotti, verificare
> che `result.incomplete` sia `False`, leggere gli eventuali `errors`/`warnings`
> ed eventualmente farsi assistere da un professionista abilitato. Nessuna
> responsabilità è assunta sulla correttezza finale della dichiarazione.

## Download

Clona il repository con Git:

```powershell
git clone https://github.com/CavalierMax/easy-crypto-eurodata.git
cd easy-crypto-eurodata
```

In alternativa, dalla pagina del repository su GitHub usa **Code → Download ZIP**
ed estrai l'archivio.

## Installazione

Richiede Python 3.12 o superiore.

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e .
```

Per eseguire anche i test:

```powershell
python -m pip install -e ".[test]"
```

## Moduli

- `loader`: CSV/XLSX;
- `mapping`: configurazioni YAML per broker;
- `normalization` e `validation`: formato interno e diagnostica contestuale;
- `lifo`: inventario globale per asset, trasferimenti e cessioni;
- `rt`: RT41, RT57, RT88, RT89 e RT90;
- `rw`: consistenze al 31 dicembre e IVCA;
- `engine`: API di orchestrazione.

Gli importi e le quantità sono sempre `Decimal`. Le operazioni vengono ordinate
per data UTC, broker e ID. Un errore blocca l'asset interessato, lascia calcolare
gli altri e marca l'output complessivo come incompleto.

## Uso essenziale

```python
from decimal import Decimal
from easycrypto import ManualRTInputs, calculate_tax, load_operations

operations, load_errors = load_operations("export.csv", "config/brokers/example.yaml")
result = calculate_tax(
    operations,
    manual_rt=ManualRTInputs(rt43=Decimal("0"), rt44_col2=Decimal("0"), rt45=Decimal("0")),
    initial_errors=load_errors,
)
```

`result.incomplete` deve essere `False` prima di usare i righi come valori
definitivi. La valorizzazione RW accetta record `YearEndValuation`; in loro
assenza usa il costo residuo ed emette un'avvertenza.

Prima di compilare qualsiasi dichiarativo con questi dati: controlla
`result.errors` (bloccanti, per asset) e `result.warnings` (non bloccanti, es.
fallback di valorizzazione RW), e verifica a campione i disposals/income contro
gli export originali dei broker.

Il loader rifiuta per default file oltre 100 MiB o 500.000 righe. I limiti sono
modificabili esplicitamente tramite `max_file_size_bytes` e `max_rows`; la lettura
si ferma alla prima riga oltre il limite, senza caricare l'intero export.

## Test

```powershell
python -m pytest
```

## Sicurezza delle dipendenze

Le dipendenze applicative hanno upper bound per evitare aggiornamenti major
involontari. Nell'ambiente di sviluppo è possibile controllare le vulnerabilità
note con:

```powershell
python -m pip install pip-audit
python -m pip_audit
```

`pip-audit` è uno strumento di sviluppo e non è una dipendenza runtime del
motore fiscale.

