A traffic light as a state machine over the strings `green`, `yellow` and
`red`.

export function isValid(state: string): boolean
  True for exactly those three strings.

export function nextState(state: string): string
  `green` becomes `yellow`, `yellow` becomes `red`, `red` becomes `green`;
  any other string becomes `red`.

export function after(state: string, steps: int): string
  The state reached by applying nextState the given number of times; the
  state itself for 0 or fewer steps.

export function stepsTo(source: string, target: string): int
  How many applications of nextState take the source to the target: 0 when
  they are equal; -1 when either is not a valid state.
