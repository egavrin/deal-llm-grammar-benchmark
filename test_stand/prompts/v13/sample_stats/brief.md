Summary statistics over an int array, using the `std/math` module.

export function sumOfEven(values: int[]): int
  The sum of the even values.

export function firstNegative(values: int[]): int
  The first negative value, or -1 when there is none.

export function spread(values: int[]): int
  The absolute difference between the largest and the smallest value, or zero
  for an empty array.

export function meanOrZero(values: int[]): int
  The integer mean, the sum divided by the count with the remainder dropped,
  or zero for an empty array.

Constraints: `sumOfEven` walks the array with a `for ... of` loop and skips
odd values with `continue`. `firstNegative` scans with a `while` loop
and leaves it with `break`.
