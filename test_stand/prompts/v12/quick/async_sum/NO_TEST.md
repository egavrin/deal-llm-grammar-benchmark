# Compile-only task

This task requires async exports and await. The stand's hidden test entry is
synchronous `export function main(): null`; it cannot await these exports
(E3012). As with `../../fetch_pipeline/NO_TEST.md`, executing them requires
an external async export driver, which is outside this prompt contribution.

The reference must compile and pass grammar recognition. Runtime and functional
results are undefined, never counted as passes. See the source mapping in
`test_stand/findings/vera-prompt-import.md`.
