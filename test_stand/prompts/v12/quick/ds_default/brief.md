export function greetingWithDefault(name: string, greeting: string | null): string
  Return "<greeting>, <name>", substituting "Hello" only when greeting is null. An empty greeting is not null. Callers always supply both arguments; null represents an omitted greeting.
