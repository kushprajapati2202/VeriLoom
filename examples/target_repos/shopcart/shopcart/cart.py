"""Shopping cart and price calculation."""

from dataclasses import dataclass
from typing import Dict, List

from shopcart.catalog import Catalog, OutOfStockError
from shopcart.money import round_money

DEFAULT_TAX_RATE = 0.08


@dataclass
class CartLine:
    sku: str
    name: str
    unit_price: float
    quantity: int

    @property
    def line_total(self) -> float:
        return round_money(self.unit_price * self.quantity)


@dataclass
class CartSummary:
    subtotal: float
    tax: float
    total: float
    item_count: int


class Cart:
    """A customer's cart. Prices are captured from the catalogue when items are added."""

    def __init__(self, catalog: Catalog, tax_rate: float = DEFAULT_TAX_RATE) -> None:
        if not 0 <= tax_rate < 1:
            raise ValueError("tax_rate must be in [0, 1)")
        self.catalog = catalog
        self.tax_rate = tax_rate
        self._lines: Dict[str, CartLine] = {}

    def add_item(self, sku: str, quantity: int = 1) -> CartLine:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        product = self.catalog.get(sku)
        current = self._lines[sku].quantity if sku in self._lines else 0
        available = self.catalog.stock_of(sku)
        if current + quantity > available:
            raise OutOfStockError(sku, current + quantity, available)
        if sku in self._lines:
            self._lines[sku].quantity += quantity
        else:
            self._lines[sku] = CartLine(sku, product.name, product.unit_price, quantity)
        return self._lines[sku]

    def remove_item(self, sku: str, quantity: int = None) -> None:
        if sku not in self._lines:
            raise KeyError(sku)
        if quantity is None or quantity >= self._lines[sku].quantity:
            del self._lines[sku]
        elif quantity <= 0:
            raise ValueError("quantity must be positive")
        else:
            self._lines[sku].quantity -= quantity

    def lines(self) -> List[CartLine]:
        return [self._lines[k] for k in sorted(self._lines)]

    def is_empty(self) -> bool:
        return not self._lines

    def subtotal(self) -> float:
        return round_money(sum(line.line_total for line in self._lines.values()))

    def summary(self) -> CartSummary:
        subtotal = self.subtotal()
        tax = round_money(subtotal * self.tax_rate)
        return CartSummary(
            subtotal=subtotal,
            tax=tax,
            total=round_money(subtotal + tax),
            item_count=sum(line.quantity for line in self._lines.values()),
        )

    def clear(self) -> None:
        self._lines.clear()
