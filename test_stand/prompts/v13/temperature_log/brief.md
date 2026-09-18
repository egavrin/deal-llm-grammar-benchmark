Temperature readings in `number`, using the `std/math` module.

export function toFahrenheit(celsius: number): number
  Celsius times 1.8 plus 32.

export function hottest(readings: number[]): number
  The largest reading, or 0.0 for an empty array.

export function countAbove(readings: number[], limit: number): int
  How many readings are strictly above the limit.

export function roundedMean(readings: number[]): int
  The mean rounded to the nearest integer, halves rounding up; 0 for an empty
  array.
