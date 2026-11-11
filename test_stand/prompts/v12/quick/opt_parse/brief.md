export function parsedSuccessor(text: string): int | null
  Parse a signed decimal integer using std/json by wrapping text as the value of a JSON object. Return it plus 1, or null on invalid JSON, non-int values, or int32 overflow. Inputs are single JSON scalar tokens or malformed tokens, never object fragments.
