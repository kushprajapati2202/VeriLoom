# Robust Currency Validation and Fallback Mechanism

The current `format_money` function assumes valid currency codes and lacks error handling for unsupported or malformed inputs. This feature introduces a strict validation layer and a configurable fallback mechanism to ensure financial reporting remains consistent even when encountering unexpected currency data.

You are working in the repository checked out at `/app` (commit `b6ba8b071313`). Implement the feature below. Existing behaviour and the existing test suite must keep working.

## Requirements

### REQ-001 (must)

Implement a custom exception class 'UnsupportedCurrencyError' and update 'format_money' to validate the currency code.

Acceptance criteria:
- Raising 'UnsupportedCurrencyError' when the provided currency code is not in the supported set {'USD', 'EUR', 'INR'}.
- The exception message must include the invalid currency code provided.

### REQ-002 (must)

Introduce a 'fallback_currency' parameter to 'format_money' to allow graceful degradation.

Acceptance criteria:
- If 'fallback_currency' is provided and the primary currency is unsupported, the function must attempt to format using the fallback currency.
- If the fallback currency is also unsupported, the function must raise 'UnsupportedCurrencyError'.

## Required public interface

The feature is verified through the following names; they must exist with these signatures:

In `shopcart/money.py` (importable as `shopcart.money`):

```python
class UnsupportedCurrencyError(Exception)
def format_money(amount: float, currency: str='USD', fallback_currency: str=None) -> str
```

## Behaviour details

- Signature: format_money(amount: float, currency: str = 'USD', fallback_currency: str = None) -> str
- Example 1: format_money(10.0, 'GBP', 'USD') returns '$10.00' (Fallback triggered).
- Example 2: format_money(10.0, 'GBP', 'JPY') raises UnsupportedCurrencyError (Fallback also invalid).
- Example 3: format_money(10.0, 'USD') returns '$10.00' (No fallback needed).
- The function 'format_money' accepts an optional 'fallback_currency' string. Supported currencies are strictly 'USD', 'EUR', and 'INR'. If the primary currency is not in this set, and 'fallback_currency' is provided, the function attempts to format using the fallback. If the fallback is also not in the set, or if no fallback is provided for an invalid primary currency, an 'UnsupportedCurrencyError' is raised. The exception message must be exactly 'Unsupported currency: <currency_code>'. The existing 'round_money' logic remains unchanged, and the default currency remains 'USD'. 'INR' is a supported currency and must be formatted with the '₹' symbol.

## Edge cases to handle

- Empty string or None as currency code.
- Negative amounts combined with unsupported currencies.
- Recursive fallback attempts (e.g., primary and fallback are both invalid).

## Constraints

- Must use only standard library modules (decimal).
- Must maintain the existing rounding logic provided by 'round_money'.

## Assumptions

- The system expects 'USD', 'EUR', or 'INR' as valid codes; all others are considered invalid unless handled by the fallback.

## Out of scope

- Automatic currency conversion (e.g., USD to EUR).
- External API calls for currency validation.
