export async function doubleAsync(value: int): int
  Return value * 2.

export async function sumAwaitedDoubles(values: int[]): int
  Await doubleAsync for each element sequentially and return their sum.
  Empty input gives 0. Doubled values and the sum fit int32.
