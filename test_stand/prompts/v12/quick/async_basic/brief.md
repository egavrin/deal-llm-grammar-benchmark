export async function asyncAnswer(): int
  Return 42.

export async function awaitedAnswer(): int
  Await a direct call to asyncAnswer and return its result.
