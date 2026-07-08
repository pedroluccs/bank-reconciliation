#!/usr/bin/env python3
"""
Bank reconciliation automation.

Reads a bank statement and a general-ledger export, matches transactions
automatically, and produces a reconciliation report showing what cleared,
what is still outstanding on each side, and where amounts disagree.

Usage:
    python reconcile.py
    python reconcile.py --bank data/bank_statement.csv --ledger data/ledger.csv
    python reconcile.py --date-tolerance 5 --out reconciliation_report.csv

No third-party dependencies — standard library only.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path


CENTS = 0.005  # amount equality tolerance (half a cent) to absorb float noise


@dataclass
class Txn:
    """A single transaction from either the bank or the ledger."""
    date: date
    description: str
    reference: str
    amount: float
    source: str                     # "bank" or "ledger"
    matched: bool = field(default=False)


@dataclass
class Match:
    bank: Txn
    ledger: Txn
    date_gap: int                   # days between the two dates
    amount_delta: float             # bank - ledger (0.0 when they agree)

    @property
    def is_discrepancy(self) -> bool:
        return abs(self.amount_delta) > CENTS


def load_transactions(path: Path, source: str) -> list[Txn]:
    """Load a CSV (date, description, reference, amount) into Txn objects."""
    txns: list[Txn] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            txns.append(
                Txn(
                    date=datetime.strptime(row["date"].strip(), "%Y-%m-%d").date(),
                    description=row["description"].strip(),
                    reference=row["reference"].strip(),
                    amount=round(float(row["amount"]), 2),
                    source=source,
                )
            )
    return txns


def reconcile(bank: list[Txn], ledger: list[Txn], date_tolerance: int = 3) -> tuple[list[Match], list[Txn], list[Txn]]:
    """
    Match bank transactions against ledger transactions.

    Two passes:
      1. By reference — the strongest signal. If references match, the items are
         paired even when the amount disagrees (that pairing becomes a flagged
         discrepancy rather than two orphaned lines).
      2. By amount + date proximity — catches items with missing or differing
         references but the same value cleared around the same time.

    Returns (matches, unmatched_bank, unmatched_ledger).
    """
    matches: list[Match] = []

    # Pass 1: reference match
    ledger_by_ref: dict[str, list[Txn]] = {}
    for lt in ledger:
        if lt.reference:
            ledger_by_ref.setdefault(lt.reference, []).append(lt)

    for bt in bank:
        if not bt.reference:
            continue
        candidates = [lt for lt in ledger_by_ref.get(bt.reference, []) if not lt.matched]
        if candidates:
            lt = candidates[0]
            bt.matched = lt.matched = True
            matches.append(
                Match(bank=bt, ledger=lt,
                      date_gap=abs((bt.date - lt.date).days),
                      amount_delta=round(bt.amount - lt.amount, 2))
            )

    # Pass 2: amount + date proximity for whatever is left
    for bt in bank:
        if bt.matched:
            continue
        best = None
        for lt in ledger:
            if lt.matched:
                continue
            if abs(bt.amount - lt.amount) <= CENTS and abs((bt.date - lt.date).days) <= date_tolerance:
                gap = abs((bt.date - lt.date).days)
                if best is None or gap < best[1]:
                    best = (lt, gap)
        if best:
            lt, gap = best
            bt.matched = lt.matched = True
            matches.append(Match(bank=bt, ledger=lt, date_gap=gap, amount_delta=0.0))

    unmatched_bank = [t for t in bank if not t.matched]
    unmatched_ledger = [t for t in ledger if not t.matched]
    return matches, unmatched_bank, unmatched_ledger


def money(n: float) -> str:
    return f"{'-' if n < 0 else ' '}${abs(n):,.2f}"


def print_report(matches: list[Match], ub: list[Txn], ul: list[Txn],
                 bank: list[Txn], ledger: list[Txn], date_tolerance: int) -> None:
    clean = [m for m in matches if not m.is_discrepancy]
    disc = [m for m in matches if m.is_discrepancy]

    bank_total = round(sum(t.amount for t in bank), 2)
    ledger_total = round(sum(t.amount for t in ledger), 2)
    ub_total = round(sum(t.amount for t in ub), 2)
    ul_total = round(sum(t.amount for t in ul), 2)
    disc_net = round(sum(m.amount_delta for m in disc), 2)

    line = "=" * 68
    print(f"\n{line}\nBANK RECONCILIATION REPORT\n{line}")
    print(f"Bank statement : {len(bank):>3} lines   net {money(bank_total)}")
    print(f"Ledger export  : {len(ledger):>3} lines   net {money(ledger_total)}")
    print(f"Date tolerance : {date_tolerance} day(s)\n")

    print(f"Matched cleanly ......... {len(clean):>3}")
    print(f"Matched w/ discrepancy .. {len(disc):>3}")
    print(f"Bank only (unmatched) ... {len(ub):>3}   {money(ub_total)}")
    print(f"Ledger only (unmatched) . {len(ul):>3}   {money(ul_total)}")

    if disc:
        print(f"\n{'-'*68}\nAMOUNT DISCREPANCIES (reference matched, value differs)\n{'-'*68}")
        for m in disc:
            print(f"  {m.bank.reference:<10} bank {money(m.bank.amount)}  |  "
                  f"ledger {money(m.ledger.amount)}  |  delta {money(m.amount_delta)}")

    if ub:
        print(f"\n{'-'*68}\nON BANK, NOT IN LEDGER  (e.g. fees, interest, unrecorded)\n{'-'*68}")
        for t in ub:
            ref = t.reference or "—"
            print(f"  {t.date}  {ref:<10} {money(t.amount):>14}   {t.description}")

    if ul:
        print(f"\n{'-'*68}\nIN LEDGER, NOT ON BANK  (outstanding / not yet cleared)\n{'-'*68}")
        for t in ul:
            ref = t.reference or "—"
            print(f"  {t.date}  {ref:<10} {money(t.amount):>14}   {t.description}")

    # Reconciliation bridge: ledger movement + adjustments should equal bank movement
    reconciled = round(ledger_total + ub_total - ul_total + disc_net, 2)
    print(f"\n{line}\nRECONCILIATION BRIDGE\n{line}")
    print(f"  Ledger net movement ............ {money(ledger_total)}")
    print(f"  + Bank-only items .............. {money(ub_total)}")
    print(f"  - Ledger-only items ............ {money(-ul_total)}")
    print(f"  +/- Discrepancy adjustments .... {money(disc_net)}")
    print(f"  {'-'*40}")
    print(f"  = Expected bank movement ....... {money(reconciled)}")
    print(f"    Actual bank movement ......... {money(bank_total)}")
    status = "RECONCILED" if abs(reconciled - bank_total) <= CENTS else "OUT OF BALANCE"
    print(f"  {'-'*40}")
    print(f"  STATUS: {status}   (residual {money(round(bank_total - reconciled, 2))})")
    print(f"{line}\n")


def write_csv_report(path: Path, matches: list[Match], ub: list[Txn], ul: list[Txn]) -> None:
    """Write a per-item report with a status column for downstream review."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["status", "reference", "bank_date", "ledger_date",
                    "bank_amount", "ledger_amount", "amount_delta", "description"])
        for m in matches:
            w.writerow(["DISCREPANCY" if m.is_discrepancy else "MATCHED",
                        m.bank.reference or m.ledger.reference,
                        m.bank.date, m.ledger.date,
                        f"{m.bank.amount:.2f}", f"{m.ledger.amount:.2f}",
                        f"{m.amount_delta:.2f}", m.ledger.description])
        for t in ub:
            w.writerow(["BANK_ONLY", t.reference, t.date, "", f"{t.amount:.2f}", "", "", t.description])
        for t in ul:
            w.writerow(["LEDGER_ONLY", t.reference, "", t.date, "", f"{t.amount:.2f}", "", t.description])


def main() -> None:
    p = argparse.ArgumentParser(description="Automate bank-to-ledger reconciliation.")
    p.add_argument("--bank", type=Path, default=Path("data/bank_statement.csv"))
    p.add_argument("--ledger", type=Path, default=Path("data/ledger.csv"))
    p.add_argument("--date-tolerance", type=int, default=3,
                   help="days of slack when matching by amount + date (default 3)")
    p.add_argument("--out", type=Path, default=Path("reconciliation_report.csv"))
    args = p.parse_args()

    bank = load_transactions(args.bank, "bank")
    ledger = load_transactions(args.ledger, "ledger")

    matches, ub, ul = reconcile(bank, ledger, args.date_tolerance)
    print_report(matches, ub, ul, bank, ledger, args.date_tolerance)
    write_csv_report(args.out, matches, ub, ul)
    print(f"Per-item report written to: {args.out}\n")


if __name__ == "__main__":
    main()
