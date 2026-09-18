Wrapping text into lines, using the `std/string` module. Words are
separated by single spaces.

export function wrap(text: string, width: int): string[]
  The words packed greedily into lines of at most `width` characters, words
  on a line joined by single spaces. A word longer than the width gets a
  line of its own. Empty for an empty or blank text.

export function longestWord(text: string): string
  The longest word, the first one on a tie; empty for an empty text.

export function countChar(text: string, ch: string): int
  How many times the single-character string occurs in the text.

export function lineCount(text: string, width: int): int
  How many lines wrap produces.
