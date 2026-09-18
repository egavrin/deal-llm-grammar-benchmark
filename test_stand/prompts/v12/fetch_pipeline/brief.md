An asynchronous scoring pipeline.

Two non-exported async functions:

async function fetchScore(id: int): int
  The id multiplied by ten.

async function fetchBonus(id: int): int
  The id plus one.

export async function combinedScore(id: int): int
  Awaits both and returns their sum.

export async function totalForAll(ids: int[]): int
  Awaits the combined score of every id and returns the total.
