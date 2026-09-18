Run-length coding of int arrays. A run is a maximal stretch of equal
adjacent values.

export function runLengths(values: int[]): int[]
  Pairs of value and run length, flattened: for `[7, 7, 3]` the result is
  `[7, 2, 3, 1]`. Empty for an empty array.

export function expand(pairs: int[]): int[]
  The inverse: every value repeated its run length times.

export function longestRun(values: int[]): int
  The length of the longest run; 0 for an empty array.

export function runCount(values: int[]): int
  How many runs the array holds.
