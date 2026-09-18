Searching a sorted int array, values in non-decreasing order.

export function indexOf(sorted: int[], target: int): int
  The lowest index holding the target, or -1 when it is absent.

export function insertPosition(sorted: int[], target: int): int
  The lowest index whose value is at least the target, or the array length
  when every value is smaller.

export function holdsValue(sorted: int[], target: int): boolean
  True when the target occurs.

export function countOf(sorted: int[], target: int): int
  How many times the target occurs.

Constraints: `insertPosition` narrows a low and a high bound with a `while`
loop instead of scanning every element.
