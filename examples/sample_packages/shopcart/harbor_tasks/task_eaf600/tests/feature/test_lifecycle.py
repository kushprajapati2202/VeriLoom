import pytest
from shopcart.catalog import Catalog, Product, UnknownProductError, OutOfStockError

@pytest.fixture
def catalog():
    c = Catalog()
    c.add_product(Product("SKU1", "Item 1", 10.0), stock=10)
    return c

def test_set_status_updates_state(catalog):
    catalog.set_status("SKU1", "discontinued")
    assert catalog._status["SKU1"] == "discontinued"
    catalog.set_status("SKU1", "active")
    assert catalog._status["SKU1"] == "active"

def test_set_status_unknown_sku(catalog):
    with pytest.raises(UnknownProductError):
        catalog.set_status("NONEXISTENT", "discontinued")

def test_set_status_invalid_value(catalog):
    with pytest.raises(ValueError):
        catalog.set_status("SKU1", "invalid_status")

def test_discontinued_blocks_take(catalog):
    catalog.set_status("SKU1", "discontinued")
    with pytest.raises(ValueError, match="discontinued"):
        catalog.take("SKU1", 1)

def test_discontinued_blocks_restock(catalog):
    catalog.set_status("SKU1", "discontinued")
    with pytest.raises(ValueError, match="discontinued"):
        catalog.restock("SKU1", 1)

def test_backordered_blocks_take(catalog):
    catalog.set_status("SKU1", "backordered")
    with pytest.raises(OutOfStockError):
        catalog.take("SKU1", 1)
    # Ensure it still works if set back to active
    catalog.set_status("SKU1", "active")
    assert catalog.take("SKU1", 1) == 9

def test_default_status_is_active(catalog):
    # Verify that a newly added product is active (can take)
    assert catalog.take("SKU1", 1) == 9
