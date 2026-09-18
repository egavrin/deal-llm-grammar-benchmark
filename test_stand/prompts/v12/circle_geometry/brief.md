A geometry module working in `number`, using the `std/math` module.

export function area(radius: number): number
  The area of a circle, taking pi as 3.14159.

export function hypotenuse(a: number, b: number): number

export function roundedArea(radius: number): number
  The area rounded down after adding one half.

export function ceilingArea(radius: number): number
  The area rounded up.

export function distanceFromOrigin(x: number): number
  The absolute value of the negated coordinate.

Constraints: `area` squares the radius with the exponentiation operator.
