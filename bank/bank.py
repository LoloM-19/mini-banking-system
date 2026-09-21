"""The Bank: customer management, account handling and transaction processing."""

from __future__ import annotations

import re

from .exceptions import (
    AccountClosedError,
    AccountNotFoundError,
    BankError,
    CustomerNotFoundError,
    DuplicateCustomerError,
    InvalidAmountError,
    ValidationError,
)
from .models import (
    ACCOUNT_TYPES,
    ZERO,
    Account,
    Customer,
    SavingsAccount,
    Transaction,
    account_from_dict,
    positive_money,
    to_money,
)
from .storage import JsonStorage

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Bank:
    """Central service. If a storage object is given, state is saved after every change."""

    def __init__(self, name: str = "PyBank", storage: JsonStorage | None = None):
        self.name = name
        self._storage = storage
        self.customers: dict[str, Customer] = {}
        self.accounts: dict[str, Account] = {}
        self._next_customer = 1
        self._next_account = 1
        if storage:
            self._load()

    # ======================================================================
    # Customer management
    # ======================================================================

    def add_customer(self, name: str, email: str, phone: str = "") -> Customer:
        name = self._clean_name(name)
        email = self._clean_email(email)
        self._ensure_email_free(email)

        customer = Customer(
            customer_id=f"CUST{self._next_customer:04d}",
            name=name,
            email=email,
            phone=phone.strip(),
        )
        self._next_customer += 1
        self.customers[customer.customer_id] = customer
        self._save()
        return customer

    def get_customer(self, customer_id: str) -> Customer:
        try:
            return self.customers[customer_id.strip().upper()]
        except KeyError:
            raise CustomerNotFoundError(f"No customer with ID '{customer_id}'.") from None

    def list_customers(self) -> list[Customer]:
        return list(self.customers.values())

    def search_customers(self, query: str) -> list[Customer]:
        """Case-insensitive match against name or email."""
        query = query.strip().lower()
        return [
            c for c in self.customers.values()
            if query in c.name.lower() or query in c.email
        ]

    def update_customer(
        self,
        customer_id: str,
        name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> Customer:
        customer = self.get_customer(customer_id)
        # Validate everything first so a bad value can't leave a half-updated customer.
        new_name = self._clean_name(name) if name else customer.name
        new_email = self._clean_email(email) if email else customer.email
        if new_email != customer.email:
            self._ensure_email_free(new_email)

        customer.name = new_name
        customer.email = new_email
        if phone is not None:
            customer.phone = phone.strip()
        self._save()
        return customer

    def remove_customer(self, customer_id: str) -> None:
        """Delete a customer. All of their accounts must already be closed."""
        customer = self.get_customer(customer_id)
        owned = self.get_customer_accounts(customer.customer_id)
        if any(account.is_active for account in owned):
            raise BankError("Close all of this customer's accounts before deleting them.")
        for account in owned:
            del self.accounts[account.account_number]
        del self.customers[customer.customer_id]
        self._save()

    # ======================================================================
    # Account handling
    # ======================================================================

    def open_account(
        self,
        customer_id: str,
        account_type: str = "checking",
        initial_deposit=0,
    ) -> Account:
        customer = self.get_customer(customer_id)
        account_class = ACCOUNT_TYPES.get(account_type.strip().lower())
        if account_class is None:
            valid = ", ".join(ACCOUNT_TYPES)
            raise ValidationError(f"Unknown account type '{account_type}'. Choose: {valid}.")

        deposit = to_money(initial_deposit)
        if deposit < 0:
            raise InvalidAmountError("Initial deposit cannot be negative.")

        account = account_class(
            account_number=str(1_000_000_000 + self._next_account),
            customer_id=customer.customer_id,
        )
        if deposit > 0:
            account.deposit(deposit, "Initial deposit")
        self._next_account += 1
        self.accounts[account.account_number] = account
        self._save()
        return account

    def get_account(self, account_number: str) -> Account:
        try:
            return self.accounts[account_number.strip()]
        except KeyError:
            raise AccountNotFoundError(f"No account with number '{account_number}'.") from None

    def get_customer_accounts(self, customer_id: str) -> list[Account]:
        customer_id = customer_id.strip().upper()
        return [a for a in self.accounts.values() if a.customer_id == customer_id]

    def close_account(self, account_number: str) -> Account:
        account = self.get_account(account_number)
        account.close()
        self._save()
        return account

    def total_balance(self, customer_id: str):
        """Sum of the balances of all of a customer's active accounts."""
        self.get_customer(customer_id)
        return sum(
            (a.balance for a in self.get_customer_accounts(customer_id) if a.is_active),
            ZERO,
        )

    # ======================================================================
    # Transaction processing
    # ======================================================================

    def deposit(self, account_number: str, amount) -> Transaction:
        tx = self.get_account(account_number).deposit(amount)
        self._save()
        return tx

    def withdraw(self, account_number: str, amount) -> Transaction:
        tx = self.get_account(account_number).withdraw(amount)
        self._save()
        return tx

    def transfer(
        self, from_account: str, to_account: str, amount
    ) -> tuple[Transaction, Transaction]:
        """Move money between two accounts. Either both sides happen or neither does."""
        source = self.get_account(from_account)
        target = self.get_account(to_account)
        if source is target:
            raise BankError("Cannot transfer to the same account.")

        amount = positive_money(amount)
        # Check the target first: the debit below is the step that can fail on funds,
        # and the credit afterwards must never fail once money has left the source.
        if not target.is_active:
            raise AccountClosedError(f"Account {target.account_number} is closed.")

        out_tx = source.transfer_out(amount, f"Transfer to {target.account_number}")
        in_tx = target.transfer_in(amount, f"Transfer from {source.account_number}")
        self._save()
        return out_tx, in_tx

    def get_statement(self, account_number: str, limit: int | None = None) -> list[Transaction]:
        """Transactions for an account, oldest first. `limit` keeps only the latest N."""
        transactions = self.get_account(account_number).transactions
        return list(transactions[-limit:]) if limit else list(transactions)

    def apply_monthly_interest(self) -> list[Transaction]:
        """Credit one month of interest to every active savings account."""
        results = []
        for account in self.accounts.values():
            if isinstance(account, SavingsAccount) and account.is_active:
                tx = account.apply_monthly_interest()
                if tx:
                    results.append(tx)
        if results:
            self._save()
        return results

    # ======================================================================
    # Validation helpers
    # ======================================================================

    @staticmethod
    def _clean_name(name: str) -> str:
        name = (name or "").strip()
        if not name:
            raise ValidationError("Name cannot be empty.")
        return name

    @staticmethod
    def _clean_email(email: str) -> str:
        email = (email or "").strip().lower()
        if not EMAIL_PATTERN.match(email):
            raise ValidationError(f"'{email}' is not a valid email address.")
        return email

    def _ensure_email_free(self, email: str) -> None:
        if any(c.email == email for c in self.customers.values()):
            raise DuplicateCustomerError(f"A customer with email '{email}' already exists.")

    # ======================================================================
    # Persistence
    # ======================================================================

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "next_customer": self._next_customer,
            "next_account": self._next_account,
            "customers": [c.to_dict() for c in self.customers.values()],
            "accounts": [a.to_dict() for a in self.accounts.values()],
        }

    def _save(self) -> None:
        if self._storage:
            self._storage.save(self.to_dict())

    def _load(self) -> None:
        data = self._storage.load()
        if not data:
            return
        self.name = data.get("name", self.name)
        self._next_customer = data["next_customer"]
        self._next_account = data["next_account"]
        self.customers = {
            c["customer_id"]: Customer.from_dict(c) for c in data["customers"]
        }
        self.accounts = {
            a["account_number"]: account_from_dict(a) for a in data["accounts"]
        }
