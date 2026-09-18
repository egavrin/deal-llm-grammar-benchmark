A sign-up form validator that reports failures as thrown errors.

export class Signup
  An `email` string, an `age` int, and an optional `referral` string.

export function isAdult(form: Signup): boolean
  True when the age is at least 18 and no greater than 120.

export function isReferred(form: Signup): boolean
  Whether the optional referral field is present.

export function reject(reason: string): null
  Throws an error whose code is `E_SIGNUP` and whose message is the reason.

export function validate(form: Signup): string
  Rejects an out-of-range age and an empty email, and otherwise returns `ok`.

export function validationCode(form: Signup): string
  Calls `validate` and returns the caught error's code instead of letting it
  escape; returns what `validate` returned when nothing was thrown.
