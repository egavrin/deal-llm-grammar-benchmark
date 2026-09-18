Closed integer intervals.

export class Interval
  A `start` int and a `finish` int, start no greater than finish.

export function covers(interval: Interval, point: int): boolean
  True when start <= point <= finish.

export function overlaps(a: Interval, b: Interval): boolean
  True when the two share at least one point.

export function mergeTwo(a: Interval, b: Interval): Interval
  A new interval from the smaller start to the larger finish.

export function totalLength(intervals: Interval[]): int
  The sum of finish minus start over all intervals, overlaps counted twice.
