export function taxRatePercent(): int
  Return the shared named tax rate, 20.

export function priceWithTax(cents: int): int
  Return cents + cents * taxRatePercent() / 100 using integer arithmetic.
  Inputs are nonnegative and all intermediate values fit int32.

Constraints: represent the shared constant with taxRatePercent, not module state;
  priceWithTax must call it.
