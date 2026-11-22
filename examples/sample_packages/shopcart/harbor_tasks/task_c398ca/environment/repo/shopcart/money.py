"""Money helpers. Amounts are floats rounded half-up to cents."""

from decimal import Decimal, ROUND_HALF_UP


def round_money(amount: float) -> float:
    return float(Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def format_money(amount: float, currency: str = "USD") -> str:
    symbol = {"USD": "$", "EUR": "€", "INR": "₹"}.get(currency, currency + " ")
    sign = "-" if amount < 0 else ""
    return f"{sign}{symbol}{abs(round_money(amount)):,.2f}"
