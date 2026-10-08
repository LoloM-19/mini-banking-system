# Mini Banking System

A command-line banking system written in pure Python (standard library only). It covers three core areas:

- **Customer management**: add, view, search, update and delete customers
- **Account handling**: open and close checking and savings accounts
- **Transaction processing**: deposits, withdrawals, transfers, statements and monthly interest

Data is saved to a JSON file, so it survives between runs.

## Getting started

Requires Python 3.9 or newer. No third-party packages are needed.

```bash
git clone https://github.com/LoloM-19/mini-banking-system.git
cd mini-banking-system
python main.py
```

On some systems the command is `python3` instead of `python`.

## Running the tests

```bash
python -m unittest -v
```

## Project structure

```
mini-banking-system/
├── main.py              # Command-line interface (menus)
├── bank/
│   ├── bank.py          # Bank service: customers, accounts, transactions
│   ├── models.py        # Customer, Account (Checking/Savings), Transaction, money helpers
│   ├── storage.py       # JSON persistence
│   └── exceptions.py    # Custom error types
└── tests/
    └── test_bank.py     # Unit tests
```

## Account types

| Type     | Overdraft | Interest                  |
|----------|-----------|---------------------------|
| Checking | up to 100 | none                      |
| Savings  | none      | 3% per year, paid monthly |

## Design decisions

- **`Decimal` instead of `float` for money.** Floats cannot represent values like `0.10` exactly (`0.1 + 0.2 != 0.3`). Decimals keep every balance exact.
- **Separation of concerns.** The `bank` package knows nothing about the command line, so the same logic could be reused behind a web API or GUI later.
- **Inheritance for account types.** `CheckingAccount` and `SavingsAccount` extend a base `Account` and only override what differs (overdraft limit, interest).
- **Atomic transfers.** Both sides of a transfer are validated before any money moves, so a failed transfer never leaves balances half-changed.
- **Immutable transaction records.** Each balance change is logged as a frozen `Transaction`, giving a full audit trail per account.
- **Custom exceptions.** All errors inherit from `BankError`, so the interface can catch and display them cleanly.
- **Safe saving.** Data is written to a temporary file and then swapped in, so a crash mid-save can't corrupt the data file.

## Limitations and ideas for improvement

This is a learning project, not production banking software. It has no authentication, no concurrency handling, and stores data in a flat file. Possible next steps:

- Add customer login with hashed PINs
- Swap JSON storage for SQLite
- Add a REST API (FastAPI) or a GUI on top of the `bank` package
- Export statements to CSV
- Add scheduled interest and account fees

## License

Free to use for learning. Add a license file (for example MIT) if you want others to reuse the code.
