Integer matrices as arrays of rows, every row the same length.

export function identity(n: int): int[][]
  The n by n matrix with ones on the diagonal and zeros elsewhere; empty for
  n of 0 or less.

export function transpose(m: int[][]): int[][]
  Rows become columns; the empty matrix stays empty.

export function rowSums(m: int[][]): int[]
  The sum of each row, in order.

export function trace(m: int[][]): int
  The sum of the diagonal elements m[i][i] for every i that exists in both
  dimensions.
