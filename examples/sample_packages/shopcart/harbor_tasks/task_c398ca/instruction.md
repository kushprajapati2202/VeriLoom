# Implement Cart-Level Promotional Discounting

Introduce a mechanism to apply a percentage-based discount to the cart's subtotal. This requires tracking an active discount state within the Cart class and ensuring that tax calculations are applied to the discounted subtotal.

You are working in the repository checked out at `/app` (commit `b6ba8b071313`). Implement the feature below. Existing behaviour and the existing test suite must keep working.

## Requirements

### REQ-001 (must)

Add support for applying a percentage discount to the Cart.

Acceptance criteria:
- The Cart class must expose an 'apply_discount(percentage: float)' method.
- The 'subtotal()' method must return the discounted subtotal (original subtotal * (1 - discount_rate)).
- The 'summary()' method must calculate tax based on the discounted subtotal.

### REQ-002 (must)

Ensure discount state persistence and reset capability.

Acceptance criteria:
- The 'clear()' method must reset the discount to 0%.
- Applying a new discount must overwrite any existing discount.

## Behaviour details

- Rule: discount_rate = percentage / 100.0. New Subtotal = round_money(original_subtotal * (1 - discount_rate)).
- Example: Cart has items totaling 100.0. Tax rate is 0.08. Calling apply_discount(20) results in: subtotal=80.0, tax=6.4 (80 * 0.08), total=86.4.
- The Cart class maintains a private _discount_percentage attribute initialized to 0.0. The apply_discount(percentage: float) method validates that the percentage is between 0 and 100 inclusive, raising ValueError otherwise. The subtotal() method calculates the original sum of line totals and applies the discount using the formula: round_money(original_subtotal * (1 - (percentage / 100.0))). The summary() method uses this discounted subtotal to calculate tax (discounted_subtotal * tax_rate) and total. The clear() method resets the discount to 0.0. Applying a new discount replaces the previous one. For example, a 100.0 subtotal with a 20% discount results in a 80.0 subtotal and 6.4 tax at an 8% tax rate.

## Edge cases to handle

- Applying a 0% discount should result in no change to the subtotal.
- Applying a 100% discount should result in a 0.0 subtotal and 0.0 tax.
- Adding items to a cart that already has a discount applied must reflect the discount on the new total.

## Constraints

- The discount percentage must be between 0 and 100 (inclusive).
- All monetary calculations must continue to use 'round_money' to maintain consistency with existing CartLine logic.

## Assumptions

- The discount is applied to the entire subtotal before tax is calculated.
- The 'round_money' function is available for use in the new calculation logic.

## Out of scope

- Support for coupon codes or alphanumeric discount strings.
- Discounting individual items; only cart-level subtotal discounting is required.
- Persistence of discounts across different Cart instances.
