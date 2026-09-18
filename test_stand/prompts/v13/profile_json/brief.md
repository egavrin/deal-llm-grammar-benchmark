A profile record that can cross a JSON boundary, using the `std/json` module.

export class Profile
  JSON-serialisable, with a `name` string, a `score` int and an `active`
  boolean defaulting to true.

export function encode(profile: Profile): string
  Builds a table holding the name and the score and returns it as JSON text.

export function decodeScore(text: string): int
  Parses JSON text and returns its `score` field.
