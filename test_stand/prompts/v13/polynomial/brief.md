Polynomials in `number`, stored as coefficient arrays: index i holds the
coefficient of x to the power i.

export function valueAt(coefficients: number[], x: number): number
  The polynomial evaluated at x; 0.0 for an empty array.

export function degree(coefficients: number[]): int
  The highest index whose coefficient is not 0.0; -1 when there is none.

export function derivative(coefficients: number[]): number[]
  The coefficients of the derivative: index i of the result holds (i+1)
  times coefficient i+1. Empty when the input has fewer than two entries.

export function addPolys(a: number[], b: number[]): number[]
  Coefficient-wise sum, as long as the longer input.
