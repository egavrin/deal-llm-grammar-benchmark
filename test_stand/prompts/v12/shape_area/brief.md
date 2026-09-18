A module that builds on a sibling module.

A module `./shapes` is already available. It exports a class `Point` with int
fields `x` and `y`, and a function `origin(): Point`.

export function boundingArea(a: shapes.Point, b: shapes.Point): int
  The area of the rectangle spanned by the two points.

export function isOrigin(p: shapes.Point): boolean

export function translate(p: shapes.Point, dx: int, dy: int): shapes.Point
  A moved copy; the argument is left unchanged.

export function areaFromOrigin(corner: shapes.Point): int
  The area of the rectangle spanned by the origin supplied by the sibling
  module and the given corner.
