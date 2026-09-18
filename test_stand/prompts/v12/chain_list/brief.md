A singly linked chain of ints.

export class Node
  A `value` int and a `next` that is a Node or null, null by default.

export function fromArray(values: int[]): Node | null
  A chain holding the values in array order, or null for an empty array.

export function count(head: Node | null): int
  How many nodes the chain holds.

export function sum(head: Node | null): int
  The sum of the values.

export function nth(head: Node | null, index: int): int | null
  The value at the zero-based index, or null when the index is out of range.
