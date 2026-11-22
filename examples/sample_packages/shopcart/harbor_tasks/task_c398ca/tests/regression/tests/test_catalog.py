import pytest

from shopcart.catalog import Catalog, OutOfStockError, Product
from shopcart.money import format_money, round_money


def test_find_by_category_and_tag():
    c = Catalog()
    c.add_product(Product("B", "b", 1.0, category="x", tags=["new"]))
    c.add_product(Product("A", "a", 1.0, category="x"))
    c.add_product(Product("C", "c", 1.0, category="y", tags=["new"]))
    assert [p.sku for p in c.find(category="x")] == ["A", "B"]
    assert [p.sku for p in c.find(tag="new")] == ["B", "C"]


def test_take_and_restock():
    c = Catalog()
    c.add_product(Product("A", "a", 1.0), stock=5)
    assert c.take("A", 3) == 2
    with pytest.raises(OutOfStockError) as exc:
        c.take("A", 3)
    assert exc.value.available == 2
    assert c.restock("A", 10) == 12


def test_negative_price_rejected():
    with pytest.raises(ValueError):
        Catalog().add_product(Product("A", "a", -1.0))


def test_money_helpers():
    assert round_money(2.675) == 2.68
    assert format_money(1234.5) == "$1,234.50"
    assert format_money(-3, "EUR") == "-€3.00"
