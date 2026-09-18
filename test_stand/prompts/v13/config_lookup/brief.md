A reader for `key = value` configuration text, using the `std/string` module.

export function findValue(lines: string[], key: string): string | null
  A line matches when, after trimming, it starts with the key immediately
  followed by `=`. The result is everything after that `=`, trimmed, for the
  first matching line, or null when no line matches.

export function hasSection(text: string, name: string): boolean
  True when the text contains the name and ends with `]`.

export function normalize(line: string): string
  The line trimmed, with every tab character replaced by a space.

export function fieldCount(line: string, separator: string): int
  How many fields the line splits into on the separator.
