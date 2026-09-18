# Lua backend emits reserved words as identifiers

**Severity:** compiles clean, produces an artifact that cannot load.

A DEAL identifier that happens to be a Lua reserved word is emitted verbatim by
the Lua backend. The compiler reports `Compilation successful`; LuaJIT then
refuses the generated chunk.

```deal
export function gap(start: int, end: int): int {
  return end - start;
}
```

```lua
gap = __rt.function_("(int,int)->int", function(start, end)   -- invalid Lua
```

```
luajit: main.lua:17: <name> or '...' expected near 'end'
```

**Scope.** Every Lua keyword that DEAL accepts as an identifier, all 12 checked:
`end`, `local`, `then`, `nil`, `repeat`, `until`, `elseif`, `do`, `and`, `or`,
`not`, `in`. Several are ordinary names in real code — `end` for a range or
interval, `in` for a direction, `local` for a scope flag.

**Why it matters here.** No amount of grammar work prevents it, and a
compile-only measurement cannot see it: the failure appears at load time, after
the compiler has declared success. It was found by writing a hidden test whose
parameter happened to be named `end`.

**Reproduce**

```bash
printf 'export function gap(start: int, end: int): int { return end - start; }\nexport function main(): null { return null; }\n' > src/main.deal
# compile with --backend lua, then run the generated main.lua
```

Checked against DEAL compiler 73b93e6.
