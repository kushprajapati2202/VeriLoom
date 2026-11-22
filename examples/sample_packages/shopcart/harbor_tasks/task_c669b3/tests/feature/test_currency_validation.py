import pytest
from shopcart.money import format_money, UnsupportedCurrencyError

def test_unsupported_currency_raises_error():
    with pytest.raises(UnsupportedCurrencyError, match="Unsupported currency: GBP"):
        format_money(10.0, "GBP")

def test_none_currency_raises_error():
    with pytest.raises(UnsupportedCurrencyError):
        format_money(10.0, None)

def test_fallback_currency_success():
    # REQ-002: Fallback triggered
    assert format_money(10.0, "GBP", "USD") == "$10.00"
    assert format_money(10.0, "JPY", "EUR") == "€10.00"

def test_fallback_currency_invalid_raises_error():
    # REQ-002: Fallback also invalid
    with pytest.raises(UnsupportedCurrencyError):
        format_money(10.0, "GBP", "JPY")

def test_inr_support():
    # Verify INR is supported and uses ₹
    assert format_money(100.0, "INR") == "₹100.00"

def test_existing_functionality_preserved():
    assert format_money(10.0, "USD") == "$10.00"
    assert format_money(-3.5, "EUR") == "-€3.50"
