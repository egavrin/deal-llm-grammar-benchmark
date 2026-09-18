A grade book over student records.

export class Student
  A `name` string and a `scores` int array.

export function average(student: Student): int
  The integer mean of the scores, remainder dropped; 0 when there are none.

export function letter(score: int): string
  `A` for 90 and above, `B` for 80 and above, `C` for 70 and above, `F`
  otherwise.

export function best(students: Student[]): string | null
  The name of the student with the highest average, the first one on a tie;
  null when the list is empty.

export function passingCount(students: Student[], minimum: int): int
  How many students have an average of at least the minimum.
