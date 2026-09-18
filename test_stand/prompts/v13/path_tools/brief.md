File path helpers over strings with `/` as the separator, using the
`std/string` module.

export function joinPath(directory: string, name: string): string
  The directory and the name joined by a single `/`; no separator is added
  when the directory already ends with one, and an empty directory yields
  the name alone.

export function baseName(path: string): string
  The text after the last `/`, or the whole path when there is none; the
  empty path has an empty base name and a depth of 0.

export function extensionOf(path: string): string
  The text after the last `.` of the base name, or an empty string when the
  base name has no `.`.

export function depth(path: string): int
  How many `/` separators the path contains.
