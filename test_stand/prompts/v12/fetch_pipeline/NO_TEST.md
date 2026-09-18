# Not functionally testable from a DEAL entry module

Every export of this task is `async`, and a DEAL entry module must be
`main(): null` without `async`. Calling an async export from it is rejected:

    E3012: 'await' is only allowed inside an async function

The compiler's own async conformance fixtures work around this the same way:
their `main` is a no-op, and the async exports are driven externally by
`deal/lua_async_export_driver.lua`, which needs a byte-exact canonical return
descriptor per export. Wiring that into the stand is worth doing, but it is a
separate piece of machinery, not a test file.

Until then this task is measured up to **compiles** and is reported as
`no test` for the run and functional levels — never silently counted as a pass
or dropped from the denominator.
