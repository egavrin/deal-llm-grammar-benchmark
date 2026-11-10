export function emitRange(first: int, last: int, emit: (value: int) => null): null
  Call emit for each integer from first through last in order, and return null.
  Make no calls when first > last. Bounds are between -1000 and 1000.

Constraints: use a loop, and pass values to the callback rather than printing.
