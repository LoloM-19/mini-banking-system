"""Custom exceptions for the banking system.

Every error inherits from BankError, so callers can catch one type
to handle any problem the bank raises.
"""


class BankError(Exception):
    """Base class for all banking errors."""


class ValidationError(BankError):
    """Input data (name, email, account type...) is invalid."""


class InvalidAmountError(BankError):
    """An amount is not a valid, positive money value."""


class InsufficientFundsError(BankError):
    """The account cannot cover the requested withdrawal or transfer."""


class CustomerNotFoundError(BankError):
    """No customer exists with the given ID."""


class AccountNotFoundError(BankError):
    """No account exists with the given account number."""


class DuplicateCustomerError(BankError):
    """A customer with this email already exists."""


class AccountClosedError(BankError):
    """The account is closed and cannot be used."""


class AccountNotEmptyError(BankError):
    """An account with a non-zero balance cannot be closed."""
