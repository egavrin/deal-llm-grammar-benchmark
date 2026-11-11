export class DepositAccount
  Fields owner: string = "" and balance: int = 0.

export function addDeposit(account: DepositAccount, amount: int): null
  Add amount to account.balance in place, preserving owner, and return null.
  Amount may be negative; each resulting balance fits int32.
