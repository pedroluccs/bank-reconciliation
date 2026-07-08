# Bank Reconciliation Automation

Automates the match between a **bank statement** and a **general-ledger export**: it pairs the transactions, flags amount discrepancies, and separates what is still outstanding on each side — then builds a reconciliation bridge that proves the two sides tie out.

Replaces the manual line-by-line tick-and-tie an analyst would otherwise do in a spreadsheet.

Two ways to use it: a **Python command-line engine** (`reconcile.py`) and a **browser interface** (`index.html`) that runs the same logic client-side — upload two CSVs, or click *Use sample data*, and read the result on screen.

> **Live demo:** enable GitHub Pages (Settings → Pages → deploy from `main`) and open `https://<your-username>.github.io/bank-reconciliation/`.

## What it does

Given two CSVs (bank + ledger), the script:

1. **Matches by reference** — the strongest signal. When references agree it pairs the lines even if the amount differs, so a value mismatch surfaces as *one flagged discrepancy* instead of two orphaned rows.
2. **Matches by amount + date proximity** — catches items with missing or differing references that cleared for the same value around the same time (configurable day tolerance).
3. **Classifies the rest**:
   - **Bank only** — fees, interest, or unrecorded items on the statement but not the books.
   - **Ledger only** — outstanding items posted in the books but not yet cleared by the bank.
   - **Discrepancies** — reference matched, amount disagrees (e.g. a transposition error).
4. **Builds a reconciliation bridge** — ledger movement, adjusted for bank-only, ledger-only, and discrepancy items, should equal the bank movement. The report shows the residual and a `RECONCILED / OUT OF BALANCE` status.

## Example output

```
Matched cleanly .........  11
Matched w/ discrepancy ..   1
Bank only (unmatched) ...   2   -$32.65
Ledger only (unmatched) .   2    $4,150.00

AMOUNT DISCREPANCIES
  INV-1004   bank  $17,630.00  |  ledger  $17,360.00  |  delta  $270.00

RECONCILIATION BRIDGE
  Ledger net movement ............  $77,990.00
  + Bank-only items .............. -$32.65
  - Ledger-only items ............ -$4,150.00
  +/- Discrepancy adjustments ....  $270.00
  = Expected bank movement .......  $74,077.35
    Actual bank movement .........  $74,077.35
  STATUS: RECONCILED   (residual  $0.00)
```

## Run it — in the browser

Open `index.html` (double-click it, or serve the folder). Click **Use sample data** to see it work instantly, or upload your own bank and ledger CSVs. Everything runs locally in the browser — no data is uploaded anywhere.

## Run it — command line

No dependencies to install — standard library only (Python 3.9+).

```bash
python reconcile.py
```

Options:

```bash
python reconcile.py --bank data/bank_statement.csv \
                    --ledger data/ledger.csv \
                    --date-tolerance 5 \
                    --out reconciliation_report.csv
```

A per-item `reconciliation_report.csv` is written with a `status` column
(`MATCHED`, `DISCREPANCY`, `BANK_ONLY`, `LEDGER_ONLY`) for downstream review.

## Input format

Both files use the same header:

| date | description | reference | amount |
|------|-------------|-----------|--------|
| 2026-06-01 | Customer payment - Northbridge | INV-1001 | 12840.00 |

Amounts are signed cash movements (inflows positive, outflows negative).

## Data

Sample data is **synthetic** — no real bank, customer, or company information.

---

Built by **Pedro Marques** — finance analyst focused on receivables, reconciliation, and finance automation.
