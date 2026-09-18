Deterministic dice from a small linear congruential generator.

export function nextSeed(seed: int): int
  (seed * 75 + 74) modulo 65537.

export function rollFrom(seed: int): int
  A die face from 1 to 6: nextSeed(seed) modulo 6, plus 1.

export function rollMany(seed: int, count: int): int[]
  `count` rolls in sequence: the first uses the given seed, and every later
  roll uses the seed produced by nextSeed for the previous one. Empty for a
  count of 0 or less.

export function totalOf(seed: int, count: int): int
  The sum of those rolls.
