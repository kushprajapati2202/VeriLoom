"""Product catalogue and stock levels."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


class UnknownProductError(KeyError):
    """Raised when a SKU is not in the catalogue."""


class OutOfStockError(Exception):
    """Raised when more units are requested than are in stock."""

    def __init__(self, sku: str, requested: int, available: int):
        super().__init__(f"{sku}: requested {requested}, only {available} in stock")
        self.sku = sku
        self.requested = requested
        self.available = available


@dataclass
class Product:
    sku: str
    name: str
    unit_price: float
    category: str = "general"
    tags: List[str] = field(default_factory=list)


class Catalog:
    """In-memory catalogue holding products and their stock counts."""

    def __init__(self) -> None:
        self._products: Dict[str, Product] = {}
        self._stock: Dict[str, int] = {}

    def add_product(self, product: Product, stock: int = 0) -> None:
        if product.unit_price < 0:
            raise ValueError("unit_price must be non-negative")
        if stock < 0:
            raise ValueError("stock must be non-negative")
        self._products[product.sku] = product
        self._stock[product.sku] = stock

    def get(self, sku: str) -> Product:
        try:
            return self._products[sku]
        except KeyError:
            raise UnknownProductError(sku) from None

    def find(self, category: Optional[str] = None, tag: Optional[str] = None) -> List[Product]:
        items = list(self._products.values())
        if category is not None:
            items = [p for p in items if p.category == category]
        if tag is not None:
            items = [p for p in items if tag in p.tags]
        return sorted(items, key=lambda p: p.sku)

    def stock_of(self, sku: str) -> int:
        self.get(sku)
        return self._stock[sku]

    def restock(self, sku: str, quantity: int) -> int:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        self.get(sku)
        self._stock[sku] += quantity
        return self._stock[sku]

    def take(self, sku: str, quantity: int) -> int:
        """Remove units from stock, returning the remaining count."""
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        available = self.stock_of(sku)
        if quantity > available:
            raise OutOfStockError(sku, quantity, available)
        self._stock[sku] = available - quantity
        return self._stock[sku]
