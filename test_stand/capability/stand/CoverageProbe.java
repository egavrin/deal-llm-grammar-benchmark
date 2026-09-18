package stand;

import deal.ast.*;
import deal.diagnostics.CompilerDiagnostic;
import deal.lexer.Lexer;
import deal.lexer.LexResult;
import deal.parser.ParseResult;
import deal.parser.Parser;
import deal.semantic.ir.SemanticProfile;

import java.lang.reflect.RecordComponent;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

/**
 * Reports which language atoms a DEAL source file exercises.
 *
 * The walk is reflective over the AST record components rather than a
 * hand-written visitor. That is deliberate: the AST is a closed set of records
 * under {@code deal.ast}, so a generic walk cannot fall behind the language.
 * A hand-written visitor would silently under-report every construct added
 * after it was written, and {@code deal.ast.Visitor} is already in that state —
 * {@code QualifiedType} exists as a node but has no {@code visit} overload.
 *
 * Usage: java stand.CoverageProbe <file.deal>...
 * Emits one JSON object per line on stdout.
 */
public final class CoverageProbe {

    /** Location metadata, not language surface. */
    private static final Set<String> SKIP_NODES = Set.of("Span", "DiagnosticRange");

    private static final Set<String> BUILTIN_TYPES = Set.of(
            "null", "boolean", "int", "number", "string", "bytes", "table", "Error");

    private final Set<String> atoms = new TreeSet<>();
    /** import alias -> stdlib module short name, e.g. "math" for "std/math". */
    private final Map<String, String> stdAliases = new HashMap<>();

    /**
     * When set, E1044 ("unrecognized compiler directive") does not count
     * against parse_ok. The compiler's conformance fixtures carry their
     * metadata as `// @spec:` / `// @expected:` comments, which collide with
     * the compiler-directive syntax. That is a property of that corpus, not of
     * the files' DEAL validity; the diagnostics are still reported.
     */
    private boolean tolerateDirectiveNoise;

    public static void main(String[] args) throws Exception {
        boolean tolerate = false;
        List<String> files = new ArrayList<>();
        for (String arg : args) {
            if ("--ignore-directive-noise".equals(arg)) tolerate = true;
            else files.add(arg);
        }
        if (files.isEmpty()) {
            System.err.println(
                    "usage: java stand.CoverageProbe [--ignore-directive-noise] <file.deal>...");
            System.exit(2);
        }
        for (String file : files) {
            CoverageProbe probe = new CoverageProbe();
            probe.tolerateDirectiveNoise = tolerate;
            System.out.println(probe.probe(Path.of(file)));
        }
    }

    private String probe(Path file) {
        String source;
        try {
            source = Files.readString(file);
        } catch (Exception e) {
            return json(file.toString(), false, List.of("read error: " + e), Set.of());
        }

        LexResult lexed = new Lexer(source, file.toString()).tokenize();
        // The production parser shape: the v1.2 int32 contract plus real
        // directive evaluation and binding. The two-argument constructor runs
        // neither, so `@jsonable` would never bind and out-of-range int
        // literals would parse clean — both would silently distort coverage.
        ParseResult parsed = new Parser(
                lexed.tokens(), file.toString(),
                SemanticProfile.DEAL_V1_2_INT32, lexed.directiveEvents()).parse();

        List<String> diagnostics = new ArrayList<>();
        for (CompilerDiagnostic d : lexed.diagnostics()) diagnostics.add(render(d));
        for (CompilerDiagnostic d : parsed.diagnostics()) diagnostics.add(render(d));

        // Imports first: member accesses are attributed to a stdlib module only
        // when their base identifier is a known import alias.
        collectImports(parsed.program());
        walk(parsed.program());

        boolean ok = counts(lexed.diagnostics()) == 0 && counts(parsed.diagnostics()) == 0;
        return json(file.toString(), ok, diagnostics, atoms);
    }

    private long counts(List<CompilerDiagnostic> diagnostics) {
        return diagnostics.stream()
                .filter(d -> "error".equals(d.severity()))
                .filter(d -> !(tolerateDirectiveNoise && "E1044".equals(d.code())))
                .count();
    }

    private static String render(CompilerDiagnostic d) {
        return d.severity() + " " + d.code() + ": " + d.message();
    }

    private void collectImports(ProgramNode program) {
        for (StatementNode statement : program.statements()) {
            StatementNode inner = statement instanceof ExportDeclaration e
                    ? e.declaration() : statement;
            if (inner instanceof ImportDeclaration imp) {
                String path = imp.modulePath();
                if (path.startsWith("std/")) {
                    atoms.add("import:" + path);
                    stdAliases.put(imp.alias(), path.substring(4));
                } else if (path.startsWith("./") || path.startsWith("../")) {
                    // Which sibling module was imported is a property of the
                    // file, not of the language; only the capability counts.
                    atoms.add("import:local");
                } else {
                    atoms.add("import:host");
                }
            }
        }
    }

    // ------------------------------------------------------------------ walk

    private void walk(Object node) {
        if (node == null) return;

        if (node instanceof Optional<?> optional) { optional.ifPresent(this::walk); return; }
        if (node instanceof Collection<?> items) { items.forEach(this::walk); return; }
        if (node instanceof Map<?, ?> map) { map.values().forEach(this::walk); return; }

        Class<?> type = node.getClass();
        if (!type.getName().startsWith("deal.ast.")) return;

        if (type.isEnum()) {
            atoms.add(enumPrefix(type) + ":" + ((Enum<?>) node).name());
            return;
        }
        if (!type.isRecord()) return;

        String name = type.getSimpleName();
        String enclosing = type.getEnclosingClass() == null
                ? null : type.getEnclosingClass().getSimpleName();

        if ("LiteralValue".equals(enclosing)) {
            atoms.add("literal:" + name);
        } else if (enclosing != null) {
            atoms.add(enclosing.toLowerCase(Locale.ROOT) + ":" + name);
        } else if (!SKIP_NODES.contains(name)) {
            atoms.add("node:" + name);
        }

        special(node, name);

        for (RecordComponent component : type.getRecordComponents()) {
            Object value;
            try {
                value = component.getAccessor().invoke(node);
            } catch (ReflectiveOperationException e) {
                continue;
            }
            walk(value);
        }
    }

    /** Atoms that are carried by a component value rather than by a node kind. */
    private void special(Object node, String name) {
        switch (node) {
            case FunctionDeclaration f -> {
                if (f.isAsync()) atoms.add("modifier:async");
                if (f.isExternal()) atoms.add("modifier:external");
            }
            case FunctionExpr f -> {
                if (f.isAsync()) atoms.add("modifier:async");
            }
            case ClassField field -> {
                atoms.add(field.optional() ? "modifier:field-optional" : "modifier:field-required");
                if (field.defaultExpr().isPresent()) atoms.add("modifier:field-default");
            }
            case NamedType t -> {
                if (BUILTIN_TYPES.contains(t.name())) atoms.add("type:" + t.name());
                else atoms.add("type:user-named");
            }
            case MemberAccessExpr member -> {
                if (member.object() instanceof IdentifierExpr base) {
                    String module = stdAliases.get(base.name());
                    if (module != null) atoms.add("stdlib:" + module + "." + member.field());
                }
            }
            default -> { }
        }
    }

    private static String enumPrefix(Class<?> type) {
        return switch (type.getSimpleName()) {
            case "BinaryOp" -> "binop";
            case "UnaryOp" -> "unop";
            case "DeclarationDirective" -> "directive";
            default -> type.getSimpleName().toLowerCase(Locale.ROOT);
        };
    }

    // ------------------------------------------------------------------ json

    private static String json(String file, boolean ok, List<String> diagnostics,
                               Set<String> atoms) {
        StringBuilder out = new StringBuilder();
        out.append("{\"file\":").append(quote(file));
        out.append(",\"parse_ok\":").append(ok);
        out.append(",\"diagnostics\":[");
        for (int i = 0; i < diagnostics.size(); i++) {
            if (i > 0) out.append(',');
            out.append(quote(diagnostics.get(i)));
        }
        out.append("],\"atoms\":[");
        boolean first = true;
        for (String atom : atoms) {
            if (!first) out.append(',');
            first = false;
            out.append(quote(atom));
        }
        return out.append("]}").toString();
    }

    private static String quote(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) out.append(String.format("\\u%04x", (int) c));
                    else out.append(c);
                }
            }
        }
        return out.append('"').toString();
    }
}
