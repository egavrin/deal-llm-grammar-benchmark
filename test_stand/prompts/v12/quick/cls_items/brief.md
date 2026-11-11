export class PricedItem
  Fields name: string = "" and cents: int = 0.

export function costliestName(items: PricedItem[]): string | null
  Return the name of the most expensive item, choosing the first on a tie.
  Return null for an empty array; prices can be negative.
