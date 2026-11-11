export class ParsedAge
  Fields age: int | null = null and error: string | null = null.

export function parseAgeResult(text: string): ParsedAge
  Parse a signed decimal integer through std/json (wrap it as an object value).
  On success return {age: parsed value, error: null}; otherwise
  {age: null, error: "invalid age: " + text}. Inputs are single JSON scalar
  tokens or malformed tokens, never object fragments; non-int values fail.
