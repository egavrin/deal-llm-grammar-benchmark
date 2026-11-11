export class NamedPerson
  Fields name: string (default "") and nickname: string | null (default null).

export function preferredName(person: NamedPerson): string
  Return nickname when it is not null, including an empty nickname; otherwise name.
