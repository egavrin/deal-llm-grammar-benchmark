A stock list kept as an array of records.

export class Stock
  A `sku` string and a `units` int.

export function find(items: Stock[], sku: string): Stock | null
  The record with that sku, or null.

export function addUnits(items: Stock[], sku: string, count: int): null
  Adds the count to the existing record for the sku, or appends a new record
  holding the count when there is none.

export function totalUnits(items: Stock[]): int
  The sum of units over all records.

export function lowStock(items: Stock[], threshold: int): string[]
  The skus whose units are strictly below the threshold, in list order.
