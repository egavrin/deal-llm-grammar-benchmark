export function predicateCount(values: int[], predicate: (value: int) => boolean): int
  Count values for which predicate returns true. Call it exactly once per element,
  in input order, even when all earlier results were false. Empty input gives 0.
