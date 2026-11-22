"""Order placement and lifecycle."""

import itertools
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List

from shopcart.cart import Cart, CartLine


class OrderStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


class OrderError(Exception):
    """Raised for invalid order operations."""


@dataclass
class Order:
    order_id: str
    customer_id: str
    lines: List[CartLine]
    subtotal: float
    tax: float
    total: float
    status: OrderStatus = OrderStatus.PENDING
    history: List[OrderStatus] = field(default_factory=list)


class OrderService:
    """Turns carts into orders and moves them through their lifecycle."""

    def __init__(self) -> None:
        self._orders: Dict[str, Order] = {}
        self._ids = itertools.count(1)

    def place_order(self, customer_id: str, cart: Cart) -> Order:
        if cart.is_empty():
            raise OrderError("cannot place an order for an empty cart")
        summary = cart.summary()
        # Stock is only taken when the order is placed.
        for line in cart.lines():
            cart.catalog.take(line.sku, line.quantity)
        order = Order(
            order_id=f"ORD-{next(self._ids):05d}",
            customer_id=customer_id,
            lines=[CartLine(l.sku, l.name, l.unit_price, l.quantity) for l in cart.lines()],
            subtotal=summary.subtotal,
            tax=summary.tax,
            total=summary.total,
        )
        order.history.append(order.status)
        self._orders[order.order_id] = order
        cart.clear()
        return order

    def get(self, order_id: str) -> Order:
        if order_id not in self._orders:
            raise OrderError(f"unknown order {order_id}")
        return self._orders[order_id]

    def pay(self, order_id: str) -> Order:
        order = self.get(order_id)
        if order.status != OrderStatus.PENDING:
            raise OrderError(f"cannot pay an order that is {order.status.value}")
        return self._set_status(order, OrderStatus.PAID)

    def ship(self, order_id: str) -> Order:
        order = self.get(order_id)
        if order.status != OrderStatus.PAID:
            raise OrderError(f"cannot ship an order that is {order.status.value}")
        return self._set_status(order, OrderStatus.SHIPPED)

    def cancel(self, order_id: str, catalog=None) -> Order:
        order = self.get(order_id)
        if order.status in (OrderStatus.SHIPPED, OrderStatus.CANCELLED):
            raise OrderError(f"cannot cancel an order that is {order.status.value}")
        if catalog is not None:
            for line in order.lines:
                catalog.restock(line.sku, line.quantity)
        return self._set_status(order, OrderStatus.CANCELLED)

    def orders_for(self, customer_id: str) -> List[Order]:
        return [o for o in self._orders.values() if o.customer_id == customer_id]

    def _set_status(self, order: Order, status: OrderStatus) -> Order:
        order.status = status
        order.history.append(status)
        return order
