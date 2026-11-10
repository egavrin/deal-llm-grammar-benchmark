export class EncodedPair
  A JSON-serialisable class (// @jsonable) with a: int = 0 and b: int = 0.

export function encodeIntPair(pair: EncodedPair): string
  Return JSON text using EncodedPair$toJson, containing both fields and values.
  JSON object key order is immaterial.
