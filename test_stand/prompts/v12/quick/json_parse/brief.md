export class DecodedUser
  A JSON-serialisable class (// @jsonable) with id: int = 0 and name: string = "".

export function decodedUserName(text: string): string | null
  Decode text using DecodedUser$fromJson; return the name, or null on failure.
  Follow the generated decoder's schema validation and default-field behavior.
