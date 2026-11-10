export class VisitCounter
  Field count: int = 0.

export function recordVisit(counter: VisitCounter): null
  Increment count by one in place and return null.

export function visitCount(counter: VisitCounter): int
  Return count without modifying it. State is passed explicitly, never global.
