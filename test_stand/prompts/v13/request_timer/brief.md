Request timing helpers, using the `std/time` and `std/math` modules.

export function nowOrZero(enabled: boolean): int
  The current time in milliseconds when enabled, zero otherwise.

export function elapsed(startMillis: int, endMillis: int): int
  The absolute difference between the two.

export function isSlow(durationMillis: int, budgetMillis: int): boolean
  True when the duration exceeds the budget, or when the budget is zero.

export function slowCount(durations: int[], budgetMillis: int): int
  How many of the durations are slow.

Constraints: `slowCount` walks the array with a `while` loop whose index
variable is declared before the loop.
