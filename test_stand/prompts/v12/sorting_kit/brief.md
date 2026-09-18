Sorting helpers over int arrays. No function changes its argument.

export function sortedCopy(values: int[]): int[]
  A new array with the values in non-decreasing order.

export function isSorted(values: int[]): boolean
  True when the values are already in non-decreasing order; true for empty
  and single-element arrays.

export function median(values: int[]): int
  The middle value of the sorted values; for an even count the lower of the
  two middle values; 0 for an empty array.

export function kthSmallest(values: int[], k: int): int | null
  The k-th smallest value counting from 1, or null when k is out of range.

Constraints: `sortedCopy` sorts with nested loops, without calling any other
function.
