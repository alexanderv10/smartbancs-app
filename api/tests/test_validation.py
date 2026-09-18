from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.main import TransactionRequest


def test_transaction_request_requires_positive_amount():
    with pytest.raises(ValidationError):
        TransactionRequest(from_account_id=1, to_account_id=2, amount=Decimal("0"))


def test_transaction_request_accepts_valid_payload():
    request = TransactionRequest(from_account_id=1, to_account_id=2, amount=Decimal("10.50"))

    assert request.from_account_id == 1
    assert request.to_account_id == 2
    assert request.amount == Decimal("10.50")
