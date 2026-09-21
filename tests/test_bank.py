"""Unit tests. Run from the project root with:  python -m unittest -v"""

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from bank import (
    AccountClosedError,
    AccountNotEmptyError,
    AccountNotFoundError,
    Bank,
    BankError,
    CustomerNotFoundError,
    DuplicateCustomerError,
    InsufficientFundsError,
    InvalidAmountError,
    JsonStorage,
    SavingsAccount,
    TransactionType,
    ValidationError,
)
from bank.models import to_money


def D(value: str) -> Decimal:
    return Decimal(value)


class MoneyTests(unittest.TestCase):
    def test_rounds_to_two_places(self):
        self.assertEqual(to_money("10.005"), D("10.01"))

    def test_no_float_errors(self):
        self.assertEqual(to_money(0.1) + to_money(0.2), D("0.30"))

    def test_rejects_garbage(self):
        for bad in ("abc", "", "NaN", "Infinity"):
            with self.subTest(bad=bad):
                with self.assertRaises(InvalidAmountError):
                    to_money(bad)


class CustomerTests(unittest.TestCase):
    def setUp(self):
        self.bank = Bank()

    def test_add_and_get_customer(self):
        c = self.bank.add_customer("Ada Lovelace", "Ada@Example.com", "0123")
        self.assertEqual(c.customer_id, "CUST0001")
        self.assertEqual(c.email, "ada@example.com")  # normalised
        self.assertIs(self.bank.get_customer("cust0001"), c)  # case-insensitive ID

    def test_ids_increment(self):
        a = self.bank.add_customer("A", "a@x.com")
        b = self.bank.add_customer("B", "b@x.com")
        self.assertNotEqual(a.customer_id, b.customer_id)

    def test_duplicate_email_rejected(self):
        self.bank.add_customer("A", "a@x.com")
        with self.assertRaises(DuplicateCustomerError):
            self.bank.add_customer("Other", "A@X.com")

    def test_invalid_data_rejected(self):
        with self.assertRaises(ValidationError):
            self.bank.add_customer("", "a@x.com")
        with self.assertRaises(ValidationError):
            self.bank.add_customer("A", "not-an-email")

    def test_unknown_customer(self):
        with self.assertRaises(CustomerNotFoundError):
            self.bank.get_customer("CUST9999")

    def test_search(self):
        self.bank.add_customer("Ada Lovelace", "ada@x.com")
        self.bank.add_customer("Alan Turing", "alan@x.com")
        self.assertEqual(len(self.bank.search_customers("ada")), 1)
        self.assertEqual(len(self.bank.search_customers("x.com")), 2)

    def test_update_customer(self):
        c = self.bank.add_customer("A", "a@x.com")
        self.bank.update_customer(c.customer_id, name="Alice", phone="555")
        self.assertEqual(c.name, "Alice")
        self.assertEqual(c.phone, "555")
        self.assertEqual(c.email, "a@x.com")

    def test_update_to_taken_email_changes_nothing(self):
        self.bank.add_customer("A", "a@x.com")
        b = self.bank.add_customer("B", "b@x.com")
        with self.assertRaises(DuplicateCustomerError):
            self.bank.update_customer(b.customer_id, name="New", email="a@x.com")
        self.assertEqual(b.name, "B")

    def test_remove_customer_requires_closed_accounts(self):
        c = self.bank.add_customer("A", "a@x.com")
        acc = self.bank.open_account(c.customer_id)
        with self.assertRaises(BankError):
            self.bank.remove_customer(c.customer_id)
        self.bank.close_account(acc.account_number)
        self.bank.remove_customer(c.customer_id)
        self.assertEqual(self.bank.list_customers(), [])
        with self.assertRaises(AccountNotFoundError):
            self.bank.get_account(acc.account_number)


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.bank = Bank()
        self.customer = self.bank.add_customer("A", "a@x.com")
        self.cid = self.customer.customer_id

    def test_open_account_with_initial_deposit(self):
        acc = self.bank.open_account(self.cid, "savings", "250.50")
        self.assertEqual(acc.balance, D("250.50"))
        self.assertEqual(acc.account_type, "savings")
        self.assertEqual(acc.transactions[0].description, "Initial deposit")

    def test_open_account_bad_input(self):
        with self.assertRaises(ValidationError):
            self.bank.open_account(self.cid, "crypto")
        with self.assertRaises(InvalidAmountError):
            self.bank.open_account(self.cid, "checking", "-5")
        with self.assertRaises(CustomerNotFoundError):
            self.bank.open_account("CUST9999")

    def test_failed_open_does_not_consume_account_number(self):
        with self.assertRaises(InvalidAmountError):
            self.bank.open_account(self.cid, "checking", "-5")
        acc = self.bank.open_account(self.cid)
        self.assertEqual(acc.account_number, "1000000001")

    def test_customer_accounts_and_total(self):
        self.bank.open_account(self.cid, "checking", "100")
        self.bank.open_account(self.cid, "savings", "50")
        self.assertEqual(len(self.bank.get_customer_accounts(self.cid)), 2)
        self.assertEqual(self.bank.total_balance(self.cid), D("150.00"))

    def test_close_account(self):
        acc = self.bank.open_account(self.cid, "checking", "10")
        with self.assertRaises(AccountNotEmptyError):
            self.bank.close_account(acc.account_number)
        self.bank.withdraw(acc.account_number, "10")
        self.bank.close_account(acc.account_number)
        self.assertFalse(acc.is_active)

    def test_closed_account_rejects_transactions(self):
        acc = self.bank.open_account(self.cid)
        self.bank.close_account(acc.account_number)
        with self.assertRaises(AccountClosedError):
            self.bank.deposit(acc.account_number, "10")


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.bank = Bank()
        cid = self.bank.add_customer("A", "a@x.com").customer_id
        self.checking = self.bank.open_account(cid, "checking", "100")
        self.savings = self.bank.open_account(cid, "savings", "200")

    def test_deposit_and_withdraw(self):
        self.bank.deposit(self.checking.account_number, "50")
        self.bank.withdraw(self.checking.account_number, "30")
        self.assertEqual(self.checking.balance, D("120.00"))

    def test_invalid_amounts(self):
        for bad in ("0", "-10", "abc", "0.001"):
            with self.subTest(bad=bad):
                with self.assertRaises(InvalidAmountError):
                    self.bank.deposit(self.checking.account_number, bad)
                with self.assertRaises(InvalidAmountError):
                    self.bank.withdraw(self.checking.account_number, bad)
        self.assertEqual(self.checking.balance, D("100.00"))

    def test_checking_can_use_overdraft(self):
        self.bank.withdraw(self.checking.account_number, "200")  # 100 balance + 100 overdraft
        self.assertEqual(self.checking.balance, D("-100.00"))
        with self.assertRaises(InsufficientFundsError):
            self.bank.withdraw(self.checking.account_number, "0.01")

    def test_savings_has_no_overdraft(self):
        with self.assertRaises(InsufficientFundsError):
            self.bank.withdraw(self.savings.account_number, "200.01")
        self.assertEqual(self.savings.balance, D("200.00"))

    def test_transfer(self):
        out_tx, in_tx = self.bank.transfer(
            self.savings.account_number, self.checking.account_number, "75"
        )
        self.assertEqual(self.savings.balance, D("125.00"))
        self.assertEqual(self.checking.balance, D("175.00"))
        self.assertEqual(out_tx.type, TransactionType.TRANSFER_OUT)
        self.assertEqual(in_tx.type, TransactionType.TRANSFER_IN)

    def test_failed_transfer_changes_nothing(self):
        with self.assertRaises(InsufficientFundsError):
            self.bank.transfer(
                self.savings.account_number, self.checking.account_number, "500"
            )
        self.assertEqual(self.savings.balance, D("200.00"))
        self.assertEqual(self.checking.balance, D("100.00"))
        self.assertEqual(len(self.savings.transactions), 1)  # only the initial deposit

    def test_transfer_to_closed_account_changes_nothing(self):
        cid = self.checking.customer_id
        closed = self.bank.open_account(cid)
        self.bank.close_account(closed.account_number)
        with self.assertRaises(AccountClosedError):
            self.bank.transfer(
                self.checking.account_number, closed.account_number, "10"
            )
        self.assertEqual(self.checking.balance, D("100.00"))

    def test_transfer_to_same_account(self):
        with self.assertRaises(BankError):
            self.bank.transfer(
                self.checking.account_number, self.checking.account_number, "10"
            )

    def test_transfer_to_unknown_account(self):
        with self.assertRaises(AccountNotFoundError):
            self.bank.transfer(self.checking.account_number, "0000", "10")

    def test_statement(self):
        self.bank.deposit(self.checking.account_number, "10")
        self.bank.withdraw(self.checking.account_number, "5")
        statement = self.bank.get_statement(self.checking.account_number)
        self.assertEqual(
            [t.type for t in statement],
            [TransactionType.DEPOSIT, TransactionType.DEPOSIT, TransactionType.WITHDRAWAL],
        )
        self.assertEqual(statement[-1].balance_after, D("105.00"))
        self.assertEqual(len(self.bank.get_statement(self.checking.account_number, limit=1)), 1)

    def test_monthly_interest_only_for_savings(self):
        results = self.bank.apply_monthly_interest()
        self.assertEqual(len(results), 1)
        # 200.00 * 3% / 12 = 0.50
        self.assertEqual(self.savings.balance, D("200.50"))
        self.assertEqual(self.checking.balance, D("100.00"))
        self.assertEqual(results[0].type, TransactionType.INTEREST)

    def test_interest_rounding_to_zero_is_skipped(self):
        bank = Bank()
        cid = bank.add_customer("B", "b@x.com").customer_id
        acc = bank.open_account(cid, "savings", "0.10")
        self.assertIsInstance(acc, SavingsAccount)
        self.assertEqual(bank.apply_monthly_interest(), [])


class PersistenceTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bank.json"

            bank = Bank(storage=JsonStorage(str(path)))
            cid = bank.add_customer("Ada", "ada@x.com", "123").customer_id
            acc = bank.open_account(cid, "savings", "100")
            other = bank.open_account(cid, "checking")
            bank.transfer(acc.account_number, other.account_number, "40.25")

            reloaded = Bank(storage=JsonStorage(str(path)))
            self.assertEqual(reloaded.get_customer(cid).name, "Ada")
            self.assertEqual(reloaded.get_account(acc.account_number).balance, D("59.75"))
            self.assertEqual(reloaded.get_account(other.account_number).balance, D("40.25"))
            self.assertEqual(len(reloaded.get_statement(acc.account_number)), 2)
            self.assertIsInstance(reloaded.get_account(acc.account_number), SavingsAccount)

            # ID counters continue where they left off
            new_customer = reloaded.add_customer("Alan", "alan@x.com")
            self.assertEqual(new_customer.customer_id, "CUST0002")

    def test_fresh_storage_starts_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            bank = Bank(storage=JsonStorage(str(Path(folder) / "none.json")))
            self.assertEqual(bank.list_customers(), [])


if __name__ == "__main__":
    unittest.main()
