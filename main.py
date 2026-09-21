"""Command-line interface for the mini banking system.

Run with:  python main.py
"""

from bank import Bank, BankError, JsonStorage
from bank.models import format_money


def ask(label: str) -> str:
    return input(f"{label}: ").strip()


# --------------------------------------------------------------------------
# Display helpers
# --------------------------------------------------------------------------

def print_customer(bank: Bank, customer) -> None:
    print(f"\n  ID:     {customer.customer_id}")
    print(f"  Name:   {customer.name}")
    print(f"  Email:  {customer.email}")
    print(f"  Phone:  {customer.phone or '-'}")
    print(f"  Joined: {customer.created_at:%Y-%m-%d}")
    accounts = bank.get_customer_accounts(customer.customer_id)
    if accounts:
        print("  Accounts:")
        for account in accounts:
            status = "" if account.is_active else "  [CLOSED]"
            print(
                f"    {account.account_number}  {account.account_type:<9}"
                f"{format_money(account.balance):>14}{status}"
            )
    else:
        print("  Accounts: none")


def print_account(account) -> None:
    print(f"\n  Account:  {account.account_number} ({account.account_type})")
    print(f"  Owner:    {account.customer_id}")
    print(f"  Balance:  {format_money(account.balance)}")
    print(f"  Status:   {'active' if account.is_active else 'closed'}")


# --------------------------------------------------------------------------
# Customer actions
# --------------------------------------------------------------------------

def add_customer(bank: Bank) -> None:
    customer = bank.add_customer(ask("Full name"), ask("Email"), ask("Phone (optional)"))
    print(f"Customer created with ID {customer.customer_id}.")


def view_customer(bank: Bank) -> None:
    print_customer(bank, bank.get_customer(ask("Customer ID")))


def find_customers(bank: Bank) -> None:
    query = ask("Search by name/email (leave blank to list all)")
    results = bank.search_customers(query) if query else bank.list_customers()
    if not results:
        print("No customers found.")
    for customer in results:
        print(f"  {customer.customer_id}  {customer.name}  <{customer.email}>")


def update_customer(bank: Bank) -> None:
    customer_id = ask("Customer ID")
    bank.get_customer(customer_id)  # fail early if the ID doesn't exist
    print("Leave a field blank to keep its current value.")
    name = ask("New name")
    email = ask("New email")
    phone = ask("New phone")
    bank.update_customer(
        customer_id,
        name=name or None,
        email=email or None,
        phone=phone or None,
    )
    print("Customer updated.")


def delete_customer(bank: Bank) -> None:
    customer_id = ask("Customer ID")
    if ask(f"Really delete {customer_id}? (yes/no)").lower() == "yes":
        bank.remove_customer(customer_id)
        print("Customer deleted.")
    else:
        print("Cancelled.")


# --------------------------------------------------------------------------
# Account actions
# --------------------------------------------------------------------------

def open_account(bank: Bank) -> None:
    customer_id = ask("Customer ID")
    account_type = ask("Account type (checking/savings)") or "checking"
    deposit = ask("Initial deposit (default 0)") or "0"
    account = bank.open_account(customer_id, account_type, deposit)
    print(f"Opened {account.account_type} account {account.account_number}.")


def view_account(bank: Bank) -> None:
    print_account(bank.get_account(ask("Account number")))


def close_account(bank: Bank) -> None:
    account = bank.close_account(ask("Account number"))
    print(f"Account {account.account_number} closed.")


# --------------------------------------------------------------------------
# Transaction actions
# --------------------------------------------------------------------------

def deposit(bank: Bank) -> None:
    tx = bank.deposit(ask("Account number"), ask("Amount"))
    print(f"Deposited {format_money(tx.amount)}. New balance: {format_money(tx.balance_after)}")


def withdraw(bank: Bank) -> None:
    tx = bank.withdraw(ask("Account number"), ask("Amount"))
    print(f"Withdrew {format_money(tx.amount)}. New balance: {format_money(tx.balance_after)}")


def transfer(bank: Bank) -> None:
    source = ask("From account")
    target = ask("To account")
    out_tx, _ = bank.transfer(source, target, ask("Amount"))
    print(f"Transferred {format_money(out_tx.amount)}. New balance: {format_money(out_tx.balance_after)}")


def statement(bank: Bank) -> None:
    number = ask("Account number")
    transactions = bank.get_statement(number)
    print(f"\nStatement for {number}")
    if not transactions:
        print("  No transactions yet.")
    for tx in transactions:
        print(
            f"  {tx.timestamp:%Y-%m-%d %H:%M}  {tx.transaction_id}  "
            f"{tx.type.value:<13}{format_money(tx.amount):>12}"
            f"{format_money(tx.balance_after):>14}  {tx.description}"
        )


def apply_interest(bank: Bank) -> None:
    results = bank.apply_monthly_interest()
    print(f"Interest applied to {len(results)} savings account(s).")


# --------------------------------------------------------------------------
# Menus
# --------------------------------------------------------------------------

def run_menu(bank: Bank, title: str, options: dict, back_label: str = "Back") -> None:
    """Show a menu until the user chooses 0. Bank errors are shown, not crashed on."""
    while True:
        print(f"\n=== {title} ===")
        for key, (label, _) in options.items():
            print(f"  {key}. {label}")
        print(f"  0. {back_label}")

        choice = ask("Choose an option")
        if choice == "0":
            return
        if choice not in options:
            print("Invalid option.")
            continue
        try:
            options[choice][1](bank)
        except BankError as error:
            print(f"Error: {error}")


def main() -> None:
    bank = Bank(name="PyBank", storage=JsonStorage("data/bank_data.json"))

    customer_menu = {
        "1": ("Add customer", add_customer),
        "2": ("View customer", view_customer),
        "3": ("List / search customers", find_customers),
        "4": ("Update customer", update_customer),
        "5": ("Delete customer", delete_customer),
    }
    account_menu = {
        "1": ("Open account", open_account),
        "2": ("View account", view_account),
        "3": ("Close account", close_account),
    }
    transaction_menu = {
        "1": ("Deposit", deposit),
        "2": ("Withdraw", withdraw),
        "3": ("Transfer", transfer),
        "4": ("Account statement", statement),
    }
    main_menu = {
        "1": ("Customer management", lambda b: run_menu(b, "Customers", customer_menu)),
        "2": ("Account management", lambda b: run_menu(b, "Accounts", account_menu)),
        "3": ("Transactions", lambda b: run_menu(b, "Transactions", transaction_menu)),
        "4": ("Apply monthly interest (savings)", apply_interest),
    }

    print(f"Welcome to {bank.name}!")
    try:
        run_menu(bank, "Main Menu", main_menu, back_label="Exit")
    except (KeyboardInterrupt, EOFError):
        print()
    print("Goodbye!")


if __name__ == "__main__":
    main()
