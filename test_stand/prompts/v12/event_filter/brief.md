Filtering a log of events.

export class Event
  A `kind` string, an `at` int timestamp, and an optional `note` string.

export function ofKind(events: Event[], kind: string): Event[]
  The events of that kind, in log order.

export function latest(events: Event[]): Event | null
  The event with the greatest timestamp, the first one on a tie; null when
  the log is empty.

export function annotated(events: Event[]): int
  How many events carry a note.

export function inRange(events: Event[], start: int, finish: int): Event[]
  The events whose timestamp is at least start and at most finish, in log
  order.
