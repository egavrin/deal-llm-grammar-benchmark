An in-memory key/value cache built on a `table`, using the `std/table` module.

export function makeCache(): table
  A new table holding exactly two entries, `hits` and `misses`, both 0.
  The counters are ordinary entries: callers update them through `store`
  like any other key.

export function store(cache: table, key: string, value: int): null
  Writes the value under the key.

export function evict(cache: table, key: string): null
  Removes the key from the cache.

export function sizeOf(cache: table): int
  How many keys the table holds, the two counters included.

export function hitRatioPercent(cache: table): int
  Hits as an integer percentage of hits plus misses, rounded down, or zero
  when both counters are zero.
