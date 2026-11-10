export function multiplicationError(a: int, b: int): string
  Multiply a and b as ints inside try/catch. Return the caught Error.code, or an empty string if multiplication succeeds. DEAL reports int32 overflow as E8004, not VERA exception names.
