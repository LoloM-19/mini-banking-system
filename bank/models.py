"""Domain models: money helpers, Transaction, Account types and Customer."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import Enum

from .exceptions import (
    AccountClosedError,
    AccountNotEmptyError,
    InsufficientFundsError,
    InvalidAmountError,
)

CURRENCY_SYMBOL = "$"
CENT = Decimal("0.01")
ZERO = Decimal("0.00")


# --------------------------------------------------------------------------
# Money helpers
# --------------------------------------------------------------------------
# Money is stored as Decimal, never float, because floats cannot represent
# values like 0.10 exactly (0.1 + 0.2 != 0.3), which is unacceptable for a bank.

def to_money(value) -> Decimal:
    """Convert a value to a Decimal rounded to 2 decimal places."""
    try:
        amount = Decimal(str(value).strip())
        if not amount.is_finite():  # rejects NaN and Infinity
            raise InvalidOperation
        return amount.quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise InvalidAmountError(f"'{value}' is not a valid amount.") from None


def positive_money(value) -> Decimal:
    """Like to_money, but the amount must be greater than zero."""
    amount = to_money(value)
    if amount <= 0:
        raise InvalidAmountError("Amount must be greater than zero.")
    return amount


def format_money(amount: Decimal) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}{CURRENCY_SYMBOL}{abs(amount):,.2f}"


# --------------------------------------------------------------------------
# Transactions
# --------------------------------------------------------------------------

class TransactionType(str, Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    INTEREST = "interest"


@dataclass(frozen=True)
class Transaction:
    """An immutable record of one change to an account balance."""

    type: TransactionType
    amount: Decimal
    balance_after: Decimal
    description: str = ""
    transaction_id: str = field(
        default_factory=lambda: uuid.uuid4().hex[:8].upper()
    )
    timestamp: datetime = field(
        default_factory=lambda: datetime.now().replace(microsecond=0)
    )

    def to_dict(self) -> dict:
        return {
            "transaction_id": self.transaction_id,
            "type": self.type.value,
            "amount": str(self.amount),
            "balance_after": str(self.balance_after),
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Transaction":
        return cls(
            transaction_id=data["transaction_id"],
            type=TransactionType(data["type"]),
            amount=Decimal(data["amount"]),
            balance_after=Decimal(data["balance_after"]),
            description=data.get("description", ""),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


# --------------------------------------------------------------------------
# Accounts
# --------------------------------------------------------------------------

class Account:
    """Base account. Subclasses customise behaviour (overdraft, interest)."""

    account_type = "account"
    OVERDRAFT_LIMIT = ZERO

    def __init__(
        self,
        account_number: str,
        customer_id: str,
        balance=ZERO,
        transactions: list[Transaction] | None = None,
        is_active: bool = True,
    ):
        self.account_number = account_number
        self.customer_id = customer_id
        self.balance = to_money(balance)
        self.transactions = list(transactions or [])
        self.is_active = is_active

    @property
    def available_balance(self) -> Decimal:
        """Balance plus any overdraft the account is allowed to use."""
        return self.balance + self.OVERDRAFT_LIMIT

    # -- public operations --------------------------------------------------

    def deposit(self, amount, description: str = "Deposit") -> Transaction:
        return self._credit(amount, TransactionType.DEPOSIT, description)

    def withdraw(self, amount, description: str = "Withdrawal") -> Transaction:
        return self._debit(amount, TransactionType.WITHDRAWAL, description)

    def transfer_out(self, amount, description: str) -> Transaction:
        return self._debit(amount, TransactionType.TRANSFER_OUT, description)

    def transfer_in(self, amount, description: str) -> Transaction:
        return self._credit(amount, TransactionType.TRANSFER_IN, description)

    def close(self) -> None:
        if self.balance != ZERO:
            raise AccountNotEmptyError(
                f"Account {self.account_number} has a balance of "
                f"{format_money(self.balance)}. Withdraw or transfer it first."
            )
        self.is_active = False

    # -- internals ----------------------------------------------------------

    def _ensure_active(self) -> None:
        if not self.is_active:
            raise AccountClosedError(f"Account {self.account_number} is closed.")

    def _credit(self, amount, tx_type: TransactionType, description: str) -> Transaction:
        self._ensure_active()
        amount = positive_money(amount)
        self.balance += amount
        return self._record(tx_type, amount, description)

    def _debit(self, amount, tx_type: TransactionType, description: str) -> Transaction:
        self._ensure_active()
        amount = positive_money(amount)
        if amount > self.available_balance:
            raise InsufficientFundsError(
                f"Insufficient funds: available {format_money(self.available_balance)}, "
                f"requested {format_money(amount)}."
            )
        self.balance -= amount
        return self._record(tx_type, amount, description)

    def _record(self, tx_type: TransactionType, amount: Decimal, description: str) -> Transaction:
        tx = Transaction(
            type=tx_type,
            amount=amount,
            balance_after=self.balance,
            description=description,
        )
        self.transactions.append(tx)
        return tx

    # -- persistence --------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "account_type": self.account_type,
            "account_number": self.account_number,
            "customer_id": self.customer_id,
            "balance": str(self.balance),
            "is_active": self.is_active,
            "transactions": [t.to_dict() for t in self.transactions],
        }

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}({self.account_number}, "
            f"balance={format_money(self.balance)})"
        )


class CheckingAccount(Account):
    """Everyday account that may go slightly overdrawn."""

    account_type = "checking"
    OVERDRAFT_LIMIT = Decimal("100.00")


class SavingsAccount(Account):
    """Interest-earning account. No overdraft allowed."""

    account_type = "savings"
    INTEREST_RATE = Decimal("0.03")  # 3% per year

    def apply_monthly_interest(self) -> Transaction | None:
        """Credit one month of interest. Returns None if it rounds to zero."""
        interest = (self.balance * self.INTEREST_RATE / 12).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
        if interest <= 0:
            return None
        return self._credit(interest, TransactionType.INTEREST, "Monthly interest")


ACCOUNT_TYPES: dict[str, type[Account]] = {
    CheckingAccount.account_type: CheckingAccount,
    SavingsAccount.account_type: SavingsAccount,
}


def account_from_dict(data: dict) -> Account:
    """Rebuild the right Account subclass from saved data."""
    cls = ACCOUNT_TYPES[data["account_type"]]
    return cls(
        account_number=data["account_number"],
        customer_id=data["customer_id"],
        balance=data["balance"],
        transactions=[Transaction.from_dict(t) for t in data["transactions"]],
        is_active=data["is_active"],
    )


# --------------------------------------------------------------------------
# Customers
# --------------------------------------------------------------------------

@dataclass
class Customer:
    customer_id: str
    name: str
    email: str
    phone: str = ""
    created_at: datetime = field(
        default_factory=lambda: datetime.now().replace(microsecond=0)
    )

    def to_dict(self) -> dict:
        return {
            "customer_id": self.customer_id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Customer":
        return cls(
            customer_id=data["customer_id"],
            name=data["name"],
            email=data["email"],
            phone=data.get("phone", ""),
            created_at=datetime.fromisoformat(data["created_at"]),
        )
