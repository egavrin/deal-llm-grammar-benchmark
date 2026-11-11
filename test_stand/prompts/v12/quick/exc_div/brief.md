export function caughtQuotient(a: int, b: int): int
  Return a / b truncated toward zero, or 0 if evaluating the division raises an error. MIN_INT / -1 is excluded.

Constraints: Catch the runtime error with try/catch instead of checking b first.
