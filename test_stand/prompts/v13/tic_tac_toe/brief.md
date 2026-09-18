A tic-tac-toe game module. A board is nine cells in row-major order, each
holding `"X"`, `"O"`, or a single space for an empty cell.

export class Game
  A `cells` string array and a `turn` string that starts as `"X"`.

export function newGame(): Game
  A game whose nine cells are all empty and whose turn is `"X"`.

export function place(game: Game, index: int): boolean
  Rejects an index outside 0..8 and a cell that is already taken, returning
  false without changing anything. Otherwise writes the current player into the
  cell, hands the turn to the other player, and returns true.

export function lineWinner(game: Game, a: int, b: int, c: int): string | null
  The mark occupying all three of the given cells, or null when the first of
  them is empty or the three do not match.

export function winnerOf(game: Game): string | null
  Checks the three rows, the three columns and the two diagonals, and returns
  the winning mark or null.

export function isDraw(game: Game): boolean
  True only when there is no winner and no cell is still empty.

export function render(game: Game): string
  The three rows joined by newline escapes, with the cells of each row
  separated by `|`.
