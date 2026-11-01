"""Pure rendering helpers for the Schemagram TUI.

Everything here turns the project's data structures (ERDiagram, TableSchema,
query ASTs, Results) into Rich renderables or plain data.  Nothing in this module
touches Textual, so it is easy to test on its own.
"""
from __future__ import annotations

import dataclasses
import itertools
import re
from dataclasses import dataclass, field
from time import perf_counter

from rich import box
from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree as RichTree

from erdiagram.classes import Attribute, Entity, ERDiagram, Relationship
from queryexecutor.ASTNodes import (
    Aggregate, And, ColumnRef, Comparison, Difference, Intersect, Join, Literal,
    Or, Project, Relation, Select, Union,
)
from queryexecutor.Executor import Executor
from queryexecutor.classes import Result
from relationalvisualizer.classes import TableSchema

# --------------------------------------------------------------------------- #
# palette (kept in sync with the Textual theme registered in tui.py)
# --------------------------------------------------------------------------- #
P = {
    "bg": "#0e1018", "surface": "#151926", "panel": "#1b2132", "line": "#2a3350",
    "text": "#c8d3f5", "dim": "#6b7599", "muted": "#8791b5",
    "cyan": "#7dcfff", "blue": "#7aa2f7", "violet": "#bb9af7", "pink": "#f7768e",
    "orange": "#ff9e64", "gold": "#e0af68", "green": "#9ece6a", "teal": "#73daca",
}


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def gradient(s: str, c1: str, c2: str, bold: bool = True) -> Text:
    """Per-character colour gradient."""
    a, b = _rgb(c1), _rgb(c2)
    n = max(len(s) - 1, 1)
    out = Text()
    for i, ch in enumerate(s):
        r, g, bl = (round(a[k] + (b[k] - a[k]) * i / n) for k in range(3))
        out.append(ch, style=f"{'bold ' if bold else ''}#{r:02x}{g:02x}{bl:02x}")
    return out


# --------------------------------------------------------------------------- #
# ER diagram
# --------------------------------------------------------------------------- #
ER_LEGEND = Text.assemble(
    ("◆", P["gold"]), (" key  ", P["dim"]),
    ("◇", P["gold"]), (" partial key  ", P["dim"]),
    ("◎", P["cyan"]), (" multi-valued  ", P["dim"]),
    ("◌", P["muted"]), (" derived  ", P["dim"]),
    ("●", P["blue"]), (" attribute", P["dim"]),
    ("    ", ""),
    ("═", P["text"]), (" total participation  ", P["dim"]),
    ("─", P["text"]), (" partial  ", P["dim"]),
    ("◈", P["violet"]), (" identifying", P["dim"]),
)


def _attribute_text(a: Attribute) -> Text:
    t = Text()
    if a.isPrimaryKey:
        t.append("◆ ", P["gold"])
        t.append(a.name, f"bold underline {P['gold']}")
    elif a.isPartialKey:
        t.append("◇ ", P["gold"])
        t.append(a.name, f"bold underline2 {P['gold']}")
    elif a.isMultiValue:
        t.append("◎ ", P["cyan"])
        t.append(a.name, P["cyan"])
    elif a.isDerived:
        t.append("◌ ", P["muted"])
        t.append(a.name, f"italic {P['muted']}")
    else:
        t.append("● ", P["blue"])
        t.append(a.name, P["text"])
    return t


def _attribute_lines(attrs: list[Attribute], prefix: str = "", child: bool = False) -> list[Text]:
    lines: list[Text] = []
    for i, a in enumerate(attrs):
        last = i == len(attrs) - 1
        connector = ("└─ " if last else "├─ ") if child else ""
        line = Text(prefix + connector, style=P["dim"])
        line.append_text(_attribute_text(a))
        lines.append(line)
        if a.composite:
            if child:
                sub_prefix = prefix + ("   " if last else "│  ")
            else:
                sub_prefix = prefix + "  "
            lines.extend(_attribute_lines(a.composite, sub_prefix, child=True))
    return lines


def _count_attrs(attrs: list[Attribute]) -> int:
    return sum(1 + _count_attrs(a.composite) for a in attrs)


def entity_card(e: Entity) -> Panel:
    lines = _attribute_lines(e.attributes) or [Text("(no attributes)", style=f"italic {P['dim']}")]
    color = P["violet"] if e.isWeak else P["blue"]
    title = Text.assemble((f" {e.name} ", f"bold {color}"))
    if e.isWeak:
        title.append("weak ", style=f"italic {P['violet']}")
    width = max([line.cell_len for line in lines] + [title.cell_len + 2, 24]) + 4
    return Panel(
        Group(*lines),
        title=title, title_align="left",
        subtitle=Text(f" {_count_attrs(e.attributes)} attrs ", style=P["dim"]), subtitle_align="right",
        box=box.DOUBLE if e.isWeak else box.ROUNDED,
        border_style=color, padding=(0, 1), width=width,
    )


def er_cards(erd: ERDiagram):
    return Columns([entity_card(e) for e in erd.entities], equal=True, expand=False, padding=(0, 1))


def _card_chip(card: str) -> Text:
    color = P["green"] if card == "1" else P["orange"] if card.upper() in ("N", "M", "*") else P["cyan"]
    return Text(f" {card} ", style=f"bold {P['bg']} on {color}")


def _participant_name(p) -> Text:
    t = Text(p.entity, style=f"bold {P['text']}")
    if p.role:
        t.append(f" ({p.role})", style=f"italic {P['dim']}")
    return t


def _line(p, n: int = 5) -> Text:
    return Text(("═" if p.isTotalParticipation else "─") * n, style=P["muted"])


def er_relationships(erd: ERDiagram):
    """One aligned row per binary relationship, a small star for n-ary ones."""
    binary = [r for r in erd.relationships if len(r.participants) == 2]
    nary = [r for r in erd.relationships if len(r.participants) != 2]
    rows: list[Text] = []

    if binary:
        lw = max(_participant_name(p).cell_len for r in binary for p in r.participants[:1])
        rw = max(_participant_name(p).cell_len for r in binary for p in r.participants[1:])
        nw = max(len(r.name) for r in binary)
        for r in binary:
            a, b = r.participants
            diamond = P["violet"] if r.isIdentifying else P["orange"]
            glyph = "◈" if r.isIdentifying else "◇"
            left = _participant_name(a)
            right = _participant_name(b)
            row = Text(" " * (lw - left.cell_len))
            row.append_text(left)
            row.append(" ")
            row.append_text(_card_chip(a.cardinality))
            row.append_text(_line(a))
            row.append(f" {glyph} ", style=diamond)
            pad = nw - len(r.name)
            row.append(" " * (pad // 2) + r.name + " " * (pad - pad // 2), style=f"bold {diamond}")
            row.append(f" {glyph} ", style=diamond)
            row.append_text(_line(b))
            row.append_text(_card_chip(b.cardinality))
            row.append(" ")
            row.append_text(right)
            row.append(" " * (rw - right.cell_len))
            if r.attributes:
                row.append("   ⟨" + ", ".join(x.name for x in r.attributes) + "⟩", style=f"italic {P['dim']}")
            rows.append(row)

    for r in nary:
        diamond = P["violet"] if r.isIdentifying else P["orange"]
        glyph = "◈" if r.isIdentifying else "◇"
        head = Text.assemble((f"{glyph} ", diamond), (r.name, f"bold {diamond}"), (f" {glyph}", diamond))
        rows.append(Text(""))
        n = len(r.participants)
        for i, p in enumerate(r.participants):
            first, last = i == 0, i == n - 1
            row = Text()
            if first:
                row.append_text(head)
                row.append("─" if n > 1 else "")
            else:
                row.append(" " * (head.cell_len + (1 if n > 1 else 0)))
            tee = "┬" if first and not last else "└" if last else "├"
            row.append(tee + ("═" if p.isTotalParticipation else "─") * 3 + " ", style=P["muted"])
            row.append_text(_card_chip(p.cardinality))
            row.append(" ")
            row.append_text(_participant_name(p))
            rows.append(row)
        if r.attributes:
            rows.append(Text("  ⟨" + ", ".join(x.name for x in r.attributes) + "⟩", style=f"italic {P['dim']}"))

    if not rows:
        rows = [Text("No relationships defined.", style=f"italic {P['dim']}")]
    return Group(*rows)


def er_lint(erd: ERDiagram) -> list[tuple[str, str]]:
    """Cheap structural checks that explain mapper / renderer failures up front."""
    out: list[tuple[str, str]] = []
    names = [e.name for e in erd.entities]
    for dup in sorted({n for n in names if names.count(n) > 1}):
        out.append(("error", f"Entity name '{dup}' is used more than once."))
    known = set(names)
    identifying_weak: set[str] = set()
    for r in erd.relationships:
        if len(r.participants) < 2:
            out.append(("error", f"Relationship '{r.name}' needs at least two participants."))
        for p in r.participants:
            if p.entity not in known:
                out.append(("error", f"Relationship '{r.name}' refers to unknown entity '{p.entity}'."))
        if r.isIdentifying:
            identifying_weak.update(p.entity for p in r.participants)
    for e in erd.entities:
        pks = [a for a in e.attributes if a.isPrimaryKey]
        pps = [a for a in e.attributes if a.isPartialKey]
        if e.isWeak:
            if not pps:
                out.append(("warn", f"Weak entity '{e.name}' has no partial key (◇)."))
            if pks:
                out.append(("warn", f"Weak entity '{e.name}' has a primary key; use a partial key."))
            if e.name not in identifying_weak:
                out.append(("warn", f"Weak entity '{e.name}' is not in any identifying relationship."))
        else:
            if not pks:
                out.append(("warn", f"Entity '{e.name}' has no primary key (◆)."))
            if pps:
                out.append(("warn", f"Entity '{e.name}' is not weak but has a partial key."))
        for a in e.attributes:
            if (a.isPrimaryKey or a.isPartialKey) and a.isMultiValue:
                out.append(("error", f"Key attribute '{e.name}.{a.name}' cannot be multi-valued."))
    return out


def lint_panel(issues: list[tuple[str, str]]) -> Panel:
    if not issues:
        body: Text | Group = Text.assemble(("✓ ", f"bold {P['green']}"), ("All structural checks passed.", P["text"]))
        color = P["green"]
    else:
        lines = []
        for level, msg in issues:
            mark, col = ("✗", P["pink"]) if level == "error" else ("▲", P["gold"])
            lines.append(Text.assemble((f"{mark} ", f"bold {col}"), (msg, P["text"])))
        body, color = Group(*lines), (P["pink"] if any(l == "error" for l, _ in issues) else P["gold"])
    return Panel(body, title=Text(" checks ", style=f"bold {color}"), title_align="left",
                 border_style=color, padding=(0, 1), box=box.ROUNDED)


def er_stats(erd: ERDiagram) -> Text:
    weak = sum(e.isWeak for e in erd.entities)
    nary = sum(len(r.participants) > 2 for r in erd.relationships)
    attrs = sum(_count_attrs(e.attributes) for e in erd.entities)

    def row(label: str, value: object, color: str) -> Text:
        return Text.assemble((f"{label:<14}", P["dim"]), (f"{value}\n", f"bold {color}"))

    t = Text()
    t.append_text(row("entities", len(erd.entities), P["blue"]))
    t.append_text(row("  weak", weak, P["violet"]))
    t.append_text(row("relationships", len(erd.relationships), P["orange"]))
    t.append_text(row("  n-ary", nary, P["pink"]))
    t.append_text(row("attributes", attrs, P["text"]))
    t.rstrip()
    return t


# --------------------------------------------------------------------------- #
# relational schema
# --------------------------------------------------------------------------- #
def _fk_targets(table: TableSchema) -> dict[str, str]:
    refs: dict[str, str] = {}
    for fk in table.foreignKeys:
        for col, ref in zip(fk.columns, fk.refColumns):
            refs[col] = f"{fk.refTable}.{ref}"
    return refs


def _is_junction(table: TableSchema) -> bool:
    pk = [c for c in table.columns if c.isPrimaryKey]
    return len(table.foreignKeys) >= 2 and bool(pk) and all(c.isForeignKey for c in pk)


def schema_card(table: TableSchema) -> Panel:
    refs = _fk_targets(table)
    grid = Table.grid(padding=(0, 1))
    grid.add_column(no_wrap=True)
    grid.add_column(no_wrap=True)
    grid.add_column(no_wrap=True)
    for c in table.columns:
        badge = Text()
        if c.isPrimaryKey:
            badge.append(" PK " if not c.isForeignKey else " PK", style=f"bold {P['bg']} on {P['gold']}")
        if c.isForeignKey:
            badge.append(" FK ", style=f"bold {P['bg']} on {P['blue']}")
        name = Text(c.name)
        if c.isPrimaryKey:
            name.stylize(f"bold underline {P['gold']}")
        elif c.isForeignKey:
            name.stylize(f"italic {P['blue']}")
        else:
            name.stylize(P["text"])
        ref = Text(f"→ {refs[c.name]}", style=P["dim"]) if c.name in refs else Text("")
        grid.add_row(badge, name, ref)
    junction = _is_junction(table)
    color = P["violet"] if junction else P["blue"]
    title = Text.assemble((f" {table.name} ", f"bold {color}"))
    if junction:
        title.append("junction ", style=f"italic {P['violet']}")
    return Panel(grid, title=title, title_align="left", border_style=color,
                 box=box.ROUNDED, padding=(0, 1), expand=False)


def schema_cards(tables: list[TableSchema]):
    return Columns([schema_card(t) for t in tables], equal=True, expand=False, padding=(0, 1))


def schema_fk_tree(tables: list[TableSchema]):
    root = RichTree(Text.assemble(("Foreign keys", f"bold {P['text']}"), ("  child ──▶ parent", P["dim"])),
                    guide_style=P["line"])
    plain = []
    for t in tables:
        if not t.foreignKeys:
            plain.append(t.name)
            continue
        branch = root.add(Text.assemble((t.name, f"bold {P['blue']}"),
                                        (f"  {len(t.foreignKeys)} reference{'s' if len(t.foreignKeys) != 1 else ''}", P["dim"])))
        for fk in t.foreignKeys:
            left = ", ".join(fk.columns)
            right = ", ".join(fk.refColumns)
            line = Text.assemble((left, f"italic {P['blue']}"), (" ──▶ ", P["muted"]),
                                 (fk.refTable, f"bold {P['teal']}"), (f"({right})", P["dim"]))
            if fk.refTable == t.name:
                line.append("  ↺ self-reference", style=f"italic {P['orange']}")
            branch.add(line)
    if plain:
        root.add(Text.assemble(("no outgoing references: ", P["dim"]), (", ".join(plain), P["muted"])))
    return root


def schema_stats(tables: list[TableSchema]) -> Text:
    cols = sum(len(t.columns) for t in tables)
    fks = sum(len(t.foreignKeys) for t in tables)
    junctions = sum(_is_junction(t) for t in tables)

    def row(label: str, value: object, color: str) -> Text:
        return Text.assemble((f"{label:<14}", P["dim"]), (f"{value}\n", f"bold {color}"))

    t = Text()
    t.append_text(row("tables", len(tables), P["blue"]))
    t.append_text(row("  junction", junctions, P["violet"]))
    t.append_text(row("columns", cols, P["text"]))
    t.append_text(row("foreign keys", fks, P["gold"]))
    t.rstrip()
    return t


def _ident(name: str) -> str:
    return name if re.fullmatch(r"[A-Za-z_]\w*", name) else '"' + name.replace('"', '""') + '"'


def _infer_type(values: list, fallback: str = "VARCHAR(100)") -> str:
    vals = [v for v in values if v is not None]
    if not vals:
        return fallback
    if all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
        return "INTEGER"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
        return "REAL"
    longest = max(len(str(v)) for v in vals)
    for size in (10, 20, 50, 100, 255):
        if longest <= size:
            return f"VARCHAR({size})"
    return "TEXT"


def schema_sql(tables: list[TableSchema], database: dict[str, Result] | None, source: str = "") -> str:
    """CREATE TABLE script; column types are inferred from loaded sample data."""
    database = database or {}

    def column_type(table: str, col: str, refs: dict[str, str]) -> str:
        for tname, cname in ((table, col), tuple(refs[col].split(".", 1)) if col in refs else (None, None)):
            res = database.get(tname) if tname else None
            if res:
                for i, c in enumerate(res.columns):
                    if c.columnName == cname:
                        return _infer_type([row[i] for row in res.rows])
        return "VARCHAR(100)"

    # parents first where possible
    by_name = {t.name: t for t in tables}
    ordered: list[TableSchema] = []
    seen: set[str] = set()

    def visit(t: TableSchema, stack: tuple[str, ...] = ()) -> None:
        if t.name in seen or t.name in stack:
            return
        for fk in t.foreignKeys:
            parent = by_name.get(fk.refTable)
            if parent is not None and parent.name != t.name:
                visit(parent, stack + (t.name,))
        if t.name not in seen:
            seen.add(t.name)
            ordered.append(t)

    for t in tables:
        visit(t)

    out = ["-- Generated by Schemagram" + (f" from {source}" if source else ""),
           "-- Column types are inferred from loaded sample data (VARCHAR(100) when unknown).",
           "-- Review them before using this script.", ""]
    for t in ordered:
        refs = _fk_targets(t)
        lines = []
        for c in t.columns:
            ty = column_type(t.name, c.name, refs)
            lines.append(f"    {_ident(c.name)} {ty}" + (" NOT NULL" if c.isPrimaryKey else ""))
        pk = [c.name for c in t.columns if c.isPrimaryKey]
        if pk:
            lines.append(f"    PRIMARY KEY ({', '.join(_ident(c) for c in pk)})")
        for fk in t.foreignKeys:
            lines.append(f"    FOREIGN KEY ({', '.join(_ident(c) for c in fk.columns)}) "
                         f"REFERENCES {_ident(fk.refTable)} ({', '.join(_ident(c) for c in fk.refColumns)})")
        out.append(f"CREATE TABLE {_ident(t.name)} (")
        out.append(",\n".join(lines))
        out.append(");")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# --------------------------------------------------------------------------- #
# query language: formal notation, tracing, highlighting, errors, completion
# --------------------------------------------------------------------------- #
KEYWORDS = ("SELECT", "PROJECT", "JOIN", "UNION", "INTERSECT", "DIFFERENCE", "AGGREGATE")
AGG_FUNCS = ("COUNT", "SUM", "AVG", "MIN", "MAX")
OP_COLORS = {
    "SELECT": P["orange"], "PROJECT": P["violet"], "JOIN": P["green"],
    "UNION": P["pink"], "INTERSECT": P["pink"], "DIFFERENCE": P["pink"], "AGGREGATE": P["gold"],
}
SYMBOLS = {Select: "σ", Project: "π", Join: "⋈", Union: "∪", Intersect: "∩", Difference: "−", Aggregate: "γ"}
OP_NAME = {Select: "SELECT", Project: "PROJECT", Join: "JOIN", Union: "UNION",
           Intersect: "INTERSECT", Difference: "DIFFERENCE", Aggregate: "AGGREGATE"}
PRETTY_OPS = {"==": "=", "=": "=", "!=": "≠", "<=": "≤", ">=": "≥", "<": "<", ">": ">"}


def _colref(c: ColumnRef) -> str:
    return f"{c.table}.{c.name}" if c.table else c.name


def fmt_operand(o) -> str:
    if isinstance(o, ColumnRef):
        return _colref(o)
    return f'"{o.value}"' if isinstance(o, Literal) and isinstance(o.value, str) else str(o.value)


def fmt_cond(c, parent: str | None = None) -> str:
    if isinstance(c, Comparison):
        return f"{fmt_operand(c.left)} {PRETTY_OPS.get(c.operator, c.operator)} {fmt_operand(c.right)}"
    if isinstance(c, And):
        s = f"{fmt_cond(c.left, 'and')} ∧ {fmt_cond(c.right, 'and')}"
        return s
    if isinstance(c, Or):
        s = f"{fmt_cond(c.left, 'or')} ∨ {fmt_cond(c.right, 'or')}"
        return f"({s})" if parent == "and" else s
    return str(c)


def children_of(n) -> list:
    match n:
        case Select(_, q) | Project(_, q) | Aggregate(_, _, q):
            return [q]
        case Join(_, left, right) | Union(left, right) | Intersect(left, right) | Difference(left, right):
            return [left, right]
        case _:
            return []


def with_children(n, kids: list):
    match n:
        case Select() | Project() | Aggregate():
            return dataclasses.replace(n, query=kids[0])
        case Join() | Union() | Intersect() | Difference():
            return dataclasses.replace(n, left=kids[0], right=kids[1])
        case _:
            return n


def operator_symbol(n) -> str:
    return SYMBOLS.get(type(n), "▤")


def operator_color(n) -> str:
    return OP_COLORS.get(OP_NAME.get(type(n), ""), P["teal"])


def operator_args(n) -> str:
    match n:
        case Relation(name):
            return name
        case Select(cond, _):
            return fmt_cond(cond)
        case Project(cols, _):
            return ", ".join(_colref(c) for c in cols)
        case Join(cond, _, _):
            return fmt_cond(cond)
        case Aggregate(fn, col, _):
            return f"{fn}({_colref(col)})"
        case _:
            return ""


def formal(n) -> Text:
    """Relational-algebra notation, e.g. π[Name]( σ[GPA ≥ 3.5]( Student ) )."""
    col = operator_color(n)
    if isinstance(n, Relation):
        return Text(n.name, style=f"bold {P['teal']}")
    t = Text()
    sym = SYMBOLS[type(n)]
    if isinstance(n, (Select, Project, Aggregate)):
        t.append(sym, style=f"bold {col}")
        t.append("[", style=P["dim"])
        t.append(operator_args(n), style=P["text"])
        t.append("]", style=P["dim"])
        t.append("( ", style=P["dim"])
        t.append_text(formal(n.query))
        t.append(" )", style=P["dim"])
        return t
    left, right = children_of(n)
    t.append("( ", style=P["dim"])
    t.append_text(formal(left))
    t.append(f" {sym}", style=f"bold {col}")
    if isinstance(n, Join):
        t.append("[", style=P["dim"])
        t.append(operator_args(n), style=P["text"])
        t.append("]", style=P["dim"])
    t.append(" ")
    t.append_text(formal(right))
    t.append(" )", style=P["dim"])
    return t


def count_operators(n) -> int:
    return (0 if isinstance(n, Relation) else 1) + sum(count_operators(k) for k in children_of(n))


def relations_used(n) -> list[str]:
    if isinstance(n, Relation):
        return [n.name]
    seen: list[str] = []
    for k in children_of(n):
        for r in relations_used(k):
            if r not in seen:
                seen.append(r)
    return seen


@dataclass
class TraceNode:
    node: object
    result: Result | None = None
    ms: float = 0.0
    error: str | None = None
    skipped: bool = False
    children: list["TraceNode"] = field(default_factory=list)

    def first_error(self) -> "TraceNode | None":
        for k in self.children:
            if (e := k.first_error()) is not None:
                return e
        return self if self.error else None


def run_trace(database: dict[str, Result], root) -> TraceNode:
    """Execute *root* bottom-up so every operator is evaluated exactly once.

    Each operator is run by the project's own Executor on a copy of the AST whose
    children have been replaced by temporary relations holding the already-computed
    child results; that gives per-operator row counts and timings for free.
    """
    counter = itertools.count()

    def go(n) -> TraceNode:
        kids = [go(k) for k in children_of(n)]
        tn = TraceNode(n, children=kids)
        if any(k.error or k.skipped for k in kids):
            tn.skipped = True
            return tn
        scratch = dict(database)
        replacements = []
        for k in kids:
            name = f"__t{next(counter)}"
            scratch[name] = k.result
            replacements.append(Relation(name))
        t0 = perf_counter()
        try:
            tn.result = Executor(scratch).execute(with_children(n, replacements) if kids else n)
        except Exception as exc:  # reported on the node, not raised
            tn.error = f"{type(exc).__name__}: {exc}"
        tn.ms = (perf_counter() - t0) * 1000
        return tn

    return go(root)


def trace_label(tn: TraceNode) -> Text:
    n = tn.node
    col = operator_color(n)
    t = Text()
    if isinstance(n, Relation):
        t.append("▤ ", style=P["teal"])
        t.append(n.name, style=f"bold {P['teal']}")
    else:
        t.append(f"{operator_symbol(n)} ", style=f"bold {col}")
        t.append(OP_NAME[type(n)], style=f"bold {col}")
    if tn.error:
        t.append(f"  ✗ {tn.error}", style=f"bold {P['pink']}")
    elif tn.skipped:
        t.append("  ⊘ skipped", style=f"italic {P['dim']}")
    elif tn.result is not None:
        t.append(f"  {len(tn.result.rows)}×{len(tn.result.columns)}", style=f"bold {P['green']}")
        if not isinstance(n, Relation):
            t.append(f" {tn.ms:.2f}ms", style=P["dim"])
    if not isinstance(n, Relation):
        args = operator_args(n)
        if args:
            t.append(f"  {args}", style=P["muted"])
    return t


# ----- result cells ------------------------------------------------------------
def fmt_number(v) -> str:
    if isinstance(v, float):
        s = f"{v:.4f}".rstrip("0").rstrip(".")
        return s or "0"
    return str(v)


def is_numeric(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def cell_text(v, numeric_col: bool) -> Text:
    if v is None:
        return Text("∅", style=f"italic {P['dim']}", justify="right" if numeric_col else "left")
    if is_numeric(v):
        return Text(fmt_number(v), style=P["orange"], justify="right")
    return Text(str(v), style=P["text"], justify="right" if numeric_col else "left")


def column_header(col, numeric_col: bool) -> Text:
    t = Text(justify="right" if numeric_col else "left")
    if col.qualifier:
        t.append(f"{col.qualifier}.", style=P["dim"])
    t.append(col.columnName, style=f"bold {P['cyan']}")
    return t


def numeric_columns(result: Result) -> list[bool]:
    flags = []
    for i in range(len(result.columns)):
        vals = [row[i] for row in result.rows if row[i] is not None]
        flags.append(bool(vals) and all(is_numeric(v) for v in vals))
    return flags


def column_kind(values: list) -> str:
    vals = [v for v in values if v is not None]
    if not vals:
        return "∅"
    if all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
        return "int"
    if all(is_numeric(v) for v in vals):
        return "real"
    return "text"


# ----- live syntax highlighting -------------------------------------------------
_TOKEN = re.compile(
    r"""(?P<str>"[^"]*"?)
      | (?P<num>-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)
      | (?P<word>[A-Za-z_][A-Za-z0-9_]*)
      | (?P<op>==|!=|<=|>=|<|>)
      | (?P<punct>[()\[\],.])
      | (?P<ws>\s+)
      | (?P<other>.)""",
    re.VERBOSE,
)


def highlight_line(text: Text, line: str, tables: dict[str, list[str]]) -> None:
    """Colour *line* in place (used by the editor's get_line override)."""
    columns = {c for cols in tables.values() for c in cols}
    prev_word_sig = ""  # previous significant token text
    prev_prev = ""
    for m in _TOKEN.finditer(line):
        kind, s = m.lastgroup, m.group()
        start, end = m.span()
        style = None
        if kind == "str":
            style = P["green"]
        elif kind == "num":
            style = P["orange"]
        elif kind == "op":
            style = f"bold {P['pink']}"
        elif kind == "punct":
            style = P["dim"]
        elif kind == "word":
            if s in OP_COLORS:
                style = f"bold {OP_COLORS[s]}"
            elif s in ("AND", "OR"):
                style = f"bold {P['pink']}"
            elif s in AGG_FUNCS and prev_word_sig == "(" and prev_prev == "AGGREGATE":
                style = f"bold {P['gold']}"
            elif prev_word_sig == "." and prev_prev in tables and s in tables[prev_prev]:
                style = P["cyan"]
            elif s in tables:
                style = f"bold {P['teal']}"
            elif s in columns:
                style = P["cyan"]
            elif s.upper() in OP_COLORS or s.upper() in ("AND", "OR"):
                style = f"underline {P['pink']}"  # right word, wrong case
            else:
                style = P["text"]
        if style:
            text.stylize(style, start, end)
        if kind != "ws":
            prev_prev, prev_word_sig = prev_word_sig, s


_TOKEN_NAMES = {
    "LPAREN": "'('", "RPAREN": "')'", "LBRACKET": "'['", "RBRACKET": "']'", "COMMA": "','",
    "DOT": "'.'", "EOF": "the end of the query", "IDENTIFIER": "a name", "NUMBER": "a number",
    "STRING": "a string", "EQ": "'=='", "NE": "'!='", "LT": "'<'", "GT": "'>'", "LE": "'<='",
    "GE": "'>='", "AND": "AND", "OR": "OR",
}


def explain_error(source: str, exc: Exception) -> Text:
    """Turn a parser/lexer error into: the offending line, a caret, and a plain message."""
    msg = str(exc)
    m = re.search(r"\s*at position (\d+)", msg)
    pos = int(m.group(1)) if m else None
    msg = re.sub(r"\s*at position \d+", "", msg)
    msg = re.sub(r"\b([A-Z]{2,})\b", lambda mm: _TOKEN_NAMES.get(mm.group(1), mm.group(1)), msg)
    out = Text()
    if pos is not None:
        pos = min(pos, len(source))
        line_start = source.rfind("\n", 0, pos) + 1
        line_end = source.find("\n", pos)
        line_end = len(source) if line_end == -1 else line_end
        line = source[line_start:line_end]
        col = pos - line_start
        shown = line if len(line) <= 90 else line[max(0, col - 45): col + 45]
        offset = col if len(line) <= 90 else min(col, 45)
        out.append(shown + "\n", style=P["muted"])
        out.append(" " * offset + "▲ ", style=f"bold {P['pink']}")
    out.append(msg, style=f"bold {P['pink']}")
    words = {w for w in re.findall(r"[A-Za-z]+", source)}
    for kw in KEYWORDS + ("AND", "OR"):
        if kw.lower() in {w.lower() for w in words} and kw not in words:
            out.append(f"\nhint: keywords are case-sensitive — write {kw}", style=f"italic {P['gold']}")
            break
    return out


def completion_candidates(before: str, tables: dict[str, list[str]]) -> tuple[int, list[str]]:
    """Return (start_index_in_*before*, candidates) for the word ending at the cursor."""
    m = re.search(r"([A-Za-z_][A-Za-z0-9_]*)?$", before)
    prefix = m.group(1) or ""
    start = len(before) - len(prefix)
    qual = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\.$", before[:start])
    if qual:  # "Table." -> only that table's columns
        pool = tables.get(qual.group(1), [])
    else:
        pool = list(KEYWORDS) + ["AND", "OR"] + list(AGG_FUNCS) + list(tables) + sorted({c for cols in tables.values() for c in cols})
    seen: list[str] = []
    for item in pool:
        if item.lower().startswith(prefix.lower()) and item not in seen:
            seen.append(item)
    if not prefix and not qual:  # nothing typed yet: don't dump every column
        seen = [s for s in seen if s in tables or s in KEYWORDS]
    return start, seen
