import pytest
from shopcart.cart import Cart
from shopcart.catalog import Catalog, Product

@pytest.fixture
def catalog():
    c = Catalog()
    c.add_product(Product("ITEM", "Item", 100.0, category="test"), stock=10)
    return c

def test_apply_discount_calculation(catalog):
    cart = Cart(catalog, tax_rate=0.08)
    cart.add_item("ITEM", 1)
    cart.apply_discount(20)
    assert cart.subtotal() == 80.0

def test_discount_affects_summary(catalog):
    cart = Cart(catalog, tax_rate=0.08)
    cart.add_item("ITEM", 1)
    cart.apply_discount(20)
    s = cart.summary()
    assert s.subtotal == 80.0
    assert s.tax == 6.4
    assert s.total == 86.4

def test_discount_persistence_on_add(catalog):
    cart = Cart(catalog)
    cart.apply_discount(50)
    cart.add_item("ITEM", 1)
    assert cart.subtotal() == 50.0
    cart.add_item("ITEM", 1)
    assert cart.subtotal() == 100.0

def test_clear_resets_discount(catalog):
    cart = Cart(catalog)
    cart.add_item("ITEM", 1)
    cart.apply_discount(50)
    cart.clear()
    cart.add_item("ITEM", 1)
    assert cart.subtotal() == 100.0

def test_overwrite_discount(catalog):
    cart = Cart(catalog)
    cart.add_item("ITEM", 1)
    cart.apply_discount(10)
    cart.apply_discount(30)
    assert cart.subtotal() == 70.0

def test_invalid_discount_range(catalog):
    cart = Cart(catalog)
    with pytest.raises(ValueError):
        cart.apply_discount(101)
    with pytest.raises(ValueError):
        cart.apply_discount(-1)

def test_zero_and_full_discount(catalog):
    cart = Cart(catalog, tax_rate=0.1)
    cart.add_item("ITEM", 1)
    cart.apply_discount(0)
    assert cart.subtotal() == 100.0
    cart.apply_discount(100)
    assert cart.subtotal() == 0.0
    assert cart.summary().tax == 0.0
