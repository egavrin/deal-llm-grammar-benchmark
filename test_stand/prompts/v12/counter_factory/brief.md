A module of function-returning helpers.

export function makeCounter(start: int): () => int
  A function that yields the next number each time it is called, beginning one
  above `start`.

export function makeAdder(step: int): (value: int) => int
  A function that adds the fixed step to its argument.

export function applyTwice(fn: (value: int) => int, seed: int): int
  Applies the given function to the seed twice.

export function countTo(limit: int): int
  Starts a fresh counter at 0 and keeps drawing values from it while the last
  value drawn is below the limit, then returns the last value drawn. When the
  limit is 0 or less nothing is drawn and the result is 0.
