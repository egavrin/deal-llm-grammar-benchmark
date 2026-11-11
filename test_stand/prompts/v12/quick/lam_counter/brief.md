export function countingClosure(): () => int
  Return a closure that yields 1, 2, 3, ... on successive calls.
  Each factory call creates independent state.
