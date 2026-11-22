import pytest

from shopcart.cart import Cart
from shopcart.catalog import Catalog, Product
from shopcart.orders import OrderError, OrderService, OrderStatus


@pytest.fixture
def setup():
    catalog = Catalog()
    catalog.add_product(Product("MUG", "Mug", 8.00), stock=5)
    return catalog, OrderService()


def test_place_order_takes_stock_and_clears_cart(setup):
    catalog, svc = setup
    cart = Cart(catalog)
    cart.add_item("MUG", 2)
    order = svc.place_order("cust-1", cart)
    assert order.order_id == "ORD-00001"
    assert order.total == 17.28
    assert catalog.stock_of("MUG") == 3
    assert cart.is_empty()


def test_lifecycle(setup):
    catalog, svc = setup
    cart = Cart(catalog)
    cart.add_item("MUG")
    order = svc.place_order("c", cart)
    svc.pay(order.order_id)
    svc.ship(order.order_id)
    assert order.history == [OrderStatus.PENDING, OrderStatus.PAID, OrderStatus.SHIPPED]
    with pytest.raises(OrderError):
        svc.cancel(order.order_id)


def test_cannot_ship_unpaid(setup):
    catalog, svc = setup
    cart = Cart(catalog)
    cart.add_item("MUG")
    order = svc.place_order("c", cart)
    with pytest.raises(OrderError):
        svc.ship(order.order_id)


def test_cancel_restocks(setup):
    catalog, svc = setup
    cart = Cart(catalog)
    cart.add_item("MUG", 4)
    order = svc.place_order("c", cart)
    svc.cancel(order.order_id, catalog=catalog)
    assert catalog.stock_of("MUG") == 5
    assert order.status == OrderStatus.CANCELLED


def test_empty_cart_rejected(setup):
    catalog, svc = setup
    with pytest.raises(OrderError):
        svc.place_order("c", Cart(catalog))
