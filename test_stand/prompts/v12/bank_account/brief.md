A bank account whose failures are thrown errors.

export class Account
  An `owner` string and a `balance` int.

export function deposit(account: Account, amount: int): null
  Adds the amount. Throws an error with code `E_AMOUNT` when the amount is 0
  or less.

export function withdraw(account: Account, amount: int): null
  Subtracts the amount. Throws `E_AMOUNT` when the amount is 0 or less, and
  `E_FUNDS` when it exceeds the balance; in both cases the balance is left
  unchanged.

export function transfer(source: Account, target: Account, amount: int): boolean
  Withdraws from the source and deposits into the target, returning true.
  When the withdrawal throws, catches the error, changes nothing and returns
  false.

export function failureCode(account: Account, amount: int): string
  Attempts a withdrawal and returns the thrown error's code, or `ok` when
  nothing was thrown.
