export class GridPoint
  Fields x: int = 0 and y: int = 0.

export function manhattanDistance(a: GridPoint, b: GridPoint): int
  Return abs(a.x-b.x) + abs(a.y-b.y). Differences and sum fit int32.
