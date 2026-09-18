A first-in, first-out queue over an int array with a moving head.

export class Queue
  An `items` int array and a `head` int, the index of the next element to
  leave; both start empty and 0.

export function enqueue(queue: Queue, value: int): null
  Appends the value.

export function dequeue(queue: Queue): int | null
  Returns the element at the head and advances the head by one, without
  touching the array; null when the queue is empty.

export function size(queue: Queue): int
  How many elements are still waiting.

export function peek(queue: Queue): int | null
  The element at the head without removing it, or null when empty.
