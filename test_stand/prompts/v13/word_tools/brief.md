Small text helpers, using the `std/string` module.

export function wordCount(text: string): int
  How many words the text holds, words being separated by single spaces;
  leading and trailing spaces are ignored, and an empty or blank text has 0.

export function repeatText(part: string, times: int): string
  The part written `times` times in a row; empty when times is 0 or less.

export function reversed(text: string): string
  The characters in reverse order.

export function isPalindrome(text: string): boolean
  True when the text reads the same reversed, compared exactly.
