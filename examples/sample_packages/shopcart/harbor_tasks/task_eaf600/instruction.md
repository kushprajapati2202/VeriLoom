# Implement Product Lifecycle Status Tracking

To support inventory management, the Catalog needs to track the lifecycle status of products (e.g., 'active', 'discontinued', 'backordered'). This state transition logic will govern whether products can be restocked or taken from inventory.

You are working in the repository checked out at `/app` (commit `b6ba8b071313`). Implement the feature below. Existing behaviour and the existing test suite must keep working.

## Requirements

### REQ-001 (must)

Introduce a status field to the Product class and a state transition mechanism in the Catalog.

Acceptance criteria:
- Product objects must now support a 'status' attribute defaulting to 'active'.
- Catalog must provide a 'set_status(sku: str, status: str)' method to update product status.
- Calling 'set_status' on a non-existent SKU must raise UnknownProductError.

### REQ-002 (must)

Enforce state-dependent constraints on stock operations.

Acceptance criteria:
- If a product status is 'discontinued', 'take' operations must raise a ValueError.
- If a product status is 'discontinued', 'restock' operations must raise a ValueError.
- If a product status is 'backordered', 'take' operations must raise OutOfStockError regardless of current stock levels.

## Behaviour details

- Example 1: catalog.set_status('SKU1', 'discontinued') followed by catalog.take('SKU1', 1) raises ValueError('Product SKU1 is discontinued').
- Example 2: catalog.set_status('SKU1', 'backordered') followed by catalog.take('SKU1', 1) raises OutOfStockError (even if stock is 100).
- Example 3: catalog.set_status('SKU1', 'active') restores normal functionality for 'take' and 'restock'.
- The Catalog class maintains a dictionary '_status' mapping SKUs to strings. Valid status values are 'active', 'discontinued', and 'backordered'. 'set_status' raises UnknownProductError if the SKU is not present. 'set_status' raises ValueError if the status string is not one of the three allowed values. 'take' raises ValueError if status is 'discontinued'. 'restock' raises ValueError if status is 'discontinued'. 'take' raises OutOfStockError if status is 'backordered', regardless of stock level. Default status for new products is 'active'.

## Edge cases to handle

- Setting status to 'active' for a product that is already 'active' should succeed without error.
- Attempting to 'take' from a 'backordered' product when stock is 10 should still raise OutOfStockError.
- Empty string or invalid status values passed to 'set_status' must raise ValueError.

## Constraints

- Status strings are limited to: 'active', 'discontinued', 'backordered'. Any other string must raise a ValueError.
- The implementation must use the existing Catalog class structure without modifying the signature of existing methods.

## Assumptions

- The 'status' field is a simple string property on the Product dataclass.
- The Catalog maintains the status state in a new internal dictionary mapping SKUs to status strings.

## Out of scope

- Persistence of status to external databases or files.
- Automatic status transitions based on stock levels (e.g., auto-discontinuing when stock hits zero).
