import pytest

from shopcart.cart import Cart
from shopcart.catalog import Catalog, OutOfStockError, Product, UnknownProductError


@pytest.fixture
def catalog():
    c = Catalog()
    c.add_product(Product("BOOK", "Novel", 12.50, category="books"), stock=10)
    c.add_product(Product("PEN", "Pen", 1.99, category="office", tags=["sale"]), stock=100)
    c.add_product(Product("LAMP", "Desk lamp", 39.00, category="home"), stock=2)
    return c


def test_add_and_summary(catalog):
    cart = Cart(catalog)
    cart.add_item("BOOK", 2)
    cart.add_item("PEN", 3)
    s = cart.summary()
    assert s.subtotal == 30.97
    assert s.tax == 2.48
    assert s.total == 33.45
    assert s.item_count == 5


def test_adding_same_sku_merges_lines(catalog):
    cart = Cart(catalog)
    cart.add_item("PEN")
    cart.add_item("PEN", 4)
    assert [(l.sku, l.quantity) for l in cart.lines()] == [("PEN", 5)]


def test_stock_limit_enforced(catalog):
    cart = Cart(catalog)
    cart.add_item("LAMP", 2)
    with pytest.raises(OutOfStockError):
        cart.add_item("LAMP")


def test_unknown_sku(catalog):
    with pytest.raises(UnknownProductError):
        Cart(catalog).add_item("NOPE")


def test_remove_partial_and_full(catalog):
    cart = Cart(catalog)
    cart.add_item("PEN", 5)
    cart.remove_item("PEN", 2)
    assert cart.lines()[0].quantity == 3
    cart.remove_item("PEN")
    assert cart.is_empty()


def test_invalid_tax_rate(catalog):
    with pytest.raises(ValueError):
        Cart(catalog, tax_rate=1.5)


def test_zero_tax(catalog):
    cart = Cart(catalog, tax_rate=0)
    cart.add_item("LAMP")
    assert cart.summary().total == 39.00
