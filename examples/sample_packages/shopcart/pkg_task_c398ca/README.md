# Task Package: task_c398ca

**Title**: Implement Cart-Level Promotional Discounting
**Repository Commit**: `b6ba8b071313f40b015394c6806c907579462eb0`
**Feature Family**: `business_rules`
**Difficulty**: `intermediate`
**Verdict**: `VALIDATED`

## Summary
Introduce a mechanism to apply a percentage-based discount to the cart's subtotal. This requires tracking an active discount state within the Cart class and ensuring that tax calculations are applied to the discounted subtotal.

## Independent Verification
To replay and verify this package:
```bash
python scripts/replay_package.py --package pkg_task_c398ca
```
