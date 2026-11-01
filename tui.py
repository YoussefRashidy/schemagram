"""Schemagram — terminal UI.

Three workspaces in one app:

  1. ER Diagram         entity cards, relationship map, structural checks, PNG export
  2. Relational Schema  the ER → relational mapping as cards / FK map / SQL DDL
  3. Query Lab          relational-algebra editor with live highlighting, a per-operator
                        execution plan you can click through, and tab completion

Run with:  python schemagram.py   (or  python tui.py)
"""
from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path
from time import perf_counter

from rich.console import Group
from rich.style import Style
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table as RichTable
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import (
    Button, ContentSwitcher, DataTable, DirectoryTree, Footer, Input, Label,
    OptionList, Static, TabbedContent, TabPane, TextArea, Tree,
)
from textual.widgets.option_list import Option
from textual.widgets.text_area import TextAreaTheme

from erdiagram.classes import ERDiagram
from queryexecutor.ASTNodes import Relation
from queryexecutor.Lexer import Lexer
from queryexecutor.Parser import Parser
from queryexecutor.classes import Result
from queryexecutor.loader import loadDatabases
from relationalvisualizer.mapper import mapERDiagram
from schemagram_core import  renderRelationalSchema
from erdiagram.main import renderERDiagram
from tui_render import (
    P, TraceNode, cell_text, column_header, column_kind, count_operators, er_cards,
    ER_LEGEND, OP_NAME, operator_symbol, er_lint, er_relationships, er_stats, explain_error, formal, gradient,
    highlight_line, lint_panel, completion_candidates, numeric_columns, relations_used,
    run_trace, schema_cards, schema_fk_tree, schema_sql, schema_stats, trace_label,
)

BASE = Path(__file__).resolve().parent
MAX_ROWS = 2000

THEME = Theme(
    name="schemagram",
    primary=P["blue"], secondary=P["violet"], accent=P["cyan"],
    warning=P["gold"], error=P["pink"], success=P["green"],
    foreground=P["text"], background=P["bg"], surface=P["surface"], panel=P["panel"],
    dark=True,
)

EDITOR_THEME = TextAreaTheme(
    name="schemagram",
    base_style=Style(color=P["text"], bgcolor=P["surface"]),
    cursor_style=Style(color=P["bg"], bgcolor=P["cyan"]),
    cursor_line_style=Style(bgcolor=P["surface"]),
    selection_style=Style(bgcolor=P["line"]),
    bracket_matching_style=Style(bgcolor=P["line"], bold=True),
    syntax_styles={},
)


def resolve(path: str) -> Path | None:
    """Find a user-supplied path relative to the CWD first, then next to this file."""
    p = Path(path).expanduser()
    if p.exists():
        return p
    q = BASE / path
    return q if q.exists() else None


# --------------------------------------------------------------------------- #
# widgets
# --------------------------------------------------------------------------- #
class QueryEditor(TextArea):
    """TextArea with relational-algebra highlighting and Tab completion."""

    class Hint(Message):
        def __init__(self, candidates: list[str]) -> None:
            self.candidates = candidates
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(
            "", language=None, soft_wrap=True, tab_behavior="indent",
            show_line_numbers=False, highlight_cursor_line=False,
            placeholder="Type a query…  e.g.  PROJECT([Name], SELECT(GPA >= 3.5, Student))    (Tab completes, F5 runs)",
            **kwargs,
        )
        self.vocab: dict[str, list[str]] = {}
        self._cycle: dict | None = None

    def get_line(self, line_index: int) -> Text:
        text = super().get_line(line_index)
        highlight_line(text, text.plain, self.vocab)
        return text

    def set_vocab(self, vocab: dict[str, list[str]]) -> None:
        self.vocab = vocab
        self._line_cache.clear()
        self.refresh()

    async def _on_key(self, event) -> None:
        if event.key == "tab":
            event.prevent_default()
            event.stop()
            self._complete()
            return
        self._cycle = None

    def _insert(self, text: str, row: int, start: int, end: int) -> None:
        self.replace(text, (row, start), (row, end), maintain_selection_offset=False)
        self.cursor_location = (row, start + len(text))

    def _complete(self) -> None:
        row, col = self.cursor_location
        line = self.document.get_line(row)
        cyc = self._cycle
        if cyc and cyc["row"] == row and cyc["end"] == col:
            cyc["i"] = (cyc["i"] + 1) % len(cyc["cands"])
            cand = cyc["cands"][cyc["i"]]
            self._insert(cand, row, cyc["start"], col)
            cyc["end"] = cyc["start"] + len(cand)
            self.post_message(self.Hint(cyc["cands"]))
            return
        start, cands = completion_candidates(line[:col], self.vocab)
        if not cands:
            self.app.bell()
            self.post_message(self.Hint([]))
            return
        prefix = line[start:col]
        if len(cands) == 1:
            self._insert(cands[0], row, start, col)
            self.post_message(self.Hint([]))
            return
        common = os.path.commonprefix([c.lower() for c in cands])
        if len(common) > len(prefix):
            self._insert(cands[0][: len(common)], row, start, col)
            self.post_message(self.Hint(cands))
        else:  # ambiguous: start cycling through the candidates on repeated Tab
            i = 1 if cands[0] == prefix and len(cands) > 1 else 0
            self._insert(cands[i], row, start, col)
            self._cycle = {"row": row, "start": start, "end": start + len(cands[i]), "cands": cands, "i": i}
            self.post_message(self.Hint(cands))


class JsonTree(DirectoryTree):
    def filter_paths(self, paths):
        return [p for p in paths
                if not p.name.startswith(".") and p.name != "__pycache__"
                and (p.is_dir() or p.suffix.lower() in {".json", ".rql"})]


class FilePicker(ModalScreen[Path | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, start: Path) -> None:
        super().__init__()
        self.title_text = title
        self.start = start

    def compose(self) -> ComposeResult:
        with Vertical(id="picker"):
            yield Label(self.title_text, id="picker-title")
            yield JsonTree(self.start, id="picker-tree")
            yield Label("Enter: choose   ·   Esc: cancel", id="picker-hint")

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        event.stop()
        self.dismiss(event.path)

    def action_cancel(self) -> None:
        self.dismiss(None)


class HelpScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape,f1,q", "close", "Close")]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help"):
            yield Static(self._content(), id="help-body")

    @staticmethod
    def _content():
        ops = RichTable(box=None, padding=(0, 2), show_header=True, header_style=f"bold {P['dim']}")
        ops.add_column("query")
        ops.add_column("algebra")
        ops.add_column("meaning")
        rows = [
            ("<Table>", "R", "a base table", P["teal"]),
            ("SELECT(cond, q)", "σ[cond](q)", "rows of q satisfying cond", P["orange"]),
            ("PROJECT([a, T.b], q)", "π[a, T.b](q)", "keep listed columns, drop duplicates", P["violet"]),
            ("JOIN(cond, q1, q2)", "q1 ⋈[cond] q2", "theta join: cross product filtered by cond", P["green"]),
            ("UNION(q1, q2)", "q1 ∪ q2", "rows in either (same arity)", P["pink"]),
            ("INTERSECT(q1, q2)", "q1 ∩ q2", "rows in both", P["pink"]),
            ("DIFFERENCE(q1, q2)", "q1 − q2", "rows in q1 but not q2", P["pink"]),
            ("AGGREGATE(FN, col, q)", "γ[FN(col)](q)", "COUNT SUM AVG MIN MAX, NULLs ignored", P["gold"]),
        ]
        for q, a, m, c in rows:
            ops.add_row(Text(q, style=f"bold {c}"), Text(a, style=P["text"]), Text(m, style=P["dim"]))

        keys = RichTable(box=None, padding=(0, 2), show_header=False)
        keys.add_column(style=f"bold {P['cyan']}")
        keys.add_column(style=P["text"])
        for k, d in [
            ("F2 / F3 / F4", "ER diagram / relational schema / query lab   (1, 2, 3 also work outside text fields)"),
            ("F5 · Ctrl+R", "run the query"),
            ("Tab", "complete a keyword, table or column; press again to cycle"),
            ("Ctrl+L", "toggle live execution while you type"),
            ("Ctrl+E", "export the current diagram as PNG (needs Graphviz)"),
            ("Ctrl+P", "command palette, including theme switching"),
            ("click a plan node", "inspect that operator's intermediate result"),
            ("Esc", "leave the editor"),
        ]:
            keys.add_row(k, d)

        notes = Text.assemble(
            ("Conditions: ", f"bold {P['text']}"),
            ("comparisons ", P["dim"]), ("==  !=  <  >  <=  >=", P["pink"]),
            (" of columns, numbers and \"strings\", combined with ", P["dim"]), ("AND  OR  ( )", P["pink"]),
            (".\nKeywords are case-sensitive. Qualify a column as ", P["dim"]), ("Table.column", P["cyan"]),
            (" when two tables share a name. Comparing with NULL is never true.", P["dim"]),
        )
        return Group(
            Text("Query language", style=f"bold {P['cyan']}"), ops, Text(""), notes, Text(""),
            Text("Keys", style=f"bold {P['cyan']}"), keys, Text(""),
            Text("Esc to close", style=f"italic {P['dim']}"),
        )

    def action_close(self) -> None:
        self.dismiss(None)


# --------------------------------------------------------------------------- #
# app
# --------------------------------------------------------------------------- #
class SchemagramApp(App):
    TITLE = "Schemagram"
    ENABLE_COMMAND_PALETTE = True

    BINDINGS = [
        Binding("f1", "help", "Help"),
        Binding("f2", "goto('er')", "ER"),
        Binding("f3", "goto('schema')", "Schema"),
        Binding("f4", "goto('lab')", "Lab"),
        Binding("f5", "run", "Run ▶", priority=True),
        Binding("ctrl+r", "run", "Run", show=False, priority=True),
        Binding("ctrl+l", "toggle_live", "Live"),
        Binding("ctrl+e", "export", "Export PNG"),
        Binding("1", "goto('er')", show=False),
        Binding("2", "goto('schema')", show=False),
        Binding("3", "goto('lab')", show=False),
    ]

    CSS = f"""
    Screen {{ background: {P['bg']}; }}

    #brand {{ height: 3; background: {P['surface']}; border-bottom: solid {P['line']}; padding: 0 2; }}
    #logo  {{ width: 1fr; height: 3; content-align: left middle; }}
    #chips {{ width: auto; height: 3; content-align: right middle; }}

    TabbedContent {{ height: 1fr; }}
    TabbedContent > ContentTabs {{ background: {P['bg']}; }}
    TabPane {{ padding: 0; }}

    .side {{ width: 42; height: 1fr; background: #121623; border-right: solid {P['line']}; padding: 1 2; }}
    .main {{ width: 1fr; height: 1fr; padding: 1 2; }}
    .h {{ color: {P['cyan']}; text-style: bold; margin: 1 0 0 0; }}
    .h.first {{ margin-top: 0; }}
    .stats {{ margin: 0 0 0 0; }}
    .row {{ height: 3; }}
    .row Button {{ margin-right: 1; }}
    .grow {{ width: 1fr; }}

    Input {{ background: {P['bg']}; border: tall {P['line']}; }}
    Input:focus {{ border: tall {P['blue']}; }}
    Button {{ min-width: 8; }}
    OptionList {{ background: {P['bg']}; border: round {P['line']}; padding: 0 1; }}
    OptionList:focus {{ border: round {P['blue']}; }}
    #er-samples {{ height: auto; max-height: 8; }}

    #viewbar {{ height: 3; }}
    #viewbar Button {{ margin-right: 1; }}
    #sc-views {{ height: 1fr; }}
    .scroll {{ height: 1fr; }}

    /* query lab */
    #lab-side Tree {{ background: {P['bg']}; border: round {P['line']}; height: 1fr; padding: 0 1; }}
    #lab-side Tree:focus {{ border: round {P['blue']}; }}
    #snippets {{ height: 1fr; }}
    #editor {{ height: 6; background: {P['surface']}; border: round {P['line']}; padding: 0 1; }}
    #editor:focus {{ border: round {P['blue']}; }}
    #ribbon {{ height: auto; max-height: 8; padding: 0 1; margin: 1 0 0 0; }}
    #toolbar {{ height: 1; margin: 1 0 1 0; }}
    #toolbar Button {{ margin-right: 1; }}
    #livechip {{ width: auto; margin-left: 1; content-align: left middle; }}
    #results {{ height: 1fr; }}
    #grid-wrap {{ width: 1fr; height: 1fr; border: round {P['line']}; }}
    #plan-wrap {{ width: 60; height: 1fr; border: round {P['line']}; margin-left: 1; }}
    #grid {{ height: 1fr; background: {P['bg']}; }}
    #plan {{ height: 1fr; background: {P['bg']}; padding: 0 1; }}

    /* modals */
    FilePicker, HelpScreen {{ align: center middle; background: {P['bg']} 70%; }}
    #picker {{ width: 72; height: 30; background: {P['surface']}; border: round {P['blue']}; padding: 1 2; }}
    #picker-title {{ color: {P['cyan']}; text-style: bold; margin-bottom: 1; }}
    #picker-tree {{ height: 1fr; background: {P['bg']}; }}
    #picker-hint {{ color: {P['dim']}; margin-top: 1; }}
    #help {{ width: 100; max-width: 95%; height: auto; max-height: 90%; background: {P['surface']};
            border: round {P['violet']}; padding: 1 3; }}
    """

    def __init__(self) -> None:
        super().__init__()
        # project state
        self.er_path: Path | None = None
        self.er_data: dict | None = None
        self.erd: ERDiagram | None = None
        self.er_issues: list[tuple[str, str]] = []
        self.tables = []
        self.map_error: str | None = None
        self.database: dict[str, Result] | None = None
        self.db_paths: list[Path] = []
        # query lab state
        self.live = True
        self.ast = None
        self.last_result: Result | None = None
        self.history: list[str] = []
        self.examples: list[str] = []
        self._snippet_map: dict[str, str] = {}
        self._live_timer = None
        self._ribbon_hint: list[str] = []

    # ---------------------------------------------------------------- layout --
    def compose(self) -> ComposeResult:
        with Horizontal(id="brand"):
            yield Static(id="logo")
            yield Static(id="chips")

        with TabbedContent(initial="er"):
            # ---- 1. ER ------------------------------------------------------
            with TabPane("① ER Diagram", id="er"):
                with Horizontal():
                    with VerticalScroll(classes="side"):
                        yield Label("ER SOURCE", classes="h first")
                        yield Input(placeholder="path/to/er.json", id="er-path")
                        with Horizontal(classes="row"):
                            yield Button("Browse…", id="er-browse")
                            yield Button("Load", id="er-load", variant="primary")
                        yield Label("SAMPLES", classes="h")
                        yield OptionList(id="er-samples")
                        yield Label("SUMMARY", classes="h")
                        yield Static(id="er-stats", classes="stats")
                        yield Label("EXPORT", classes="h")
                        yield Input(value="out/er_diagram", id="er-out")
                        with Horizontal(classes="row"):
                            yield Button("Export PNG", id="er-export", variant="success")
                    with VerticalScroll(classes="main"):
                        yield Static(id="er-view")

            # ---- 2. relational schema ------------------------------------------
            with TabPane("② Relational Schema", id="schema"):
                with Horizontal():
                    with VerticalScroll(classes="side"):
                        yield Label("MAPPED FROM ER", classes="h first")
                        yield Static(id="sc-source")
                        yield Label("SUMMARY", classes="h")
                        yield Static(id="sc-stats", classes="stats")
                        yield Label("EXPORT", classes="h")
                        yield Input(value="out/relational_schema", id="sc-out")
                        with Horizontal(classes="row"):
                            yield Button("PNG", id="sc-export", variant="success")
                            yield Button("Save .sql", id="sc-save-sql")
                        with Horizontal(classes="row"):
                            yield Button("Copy SQL", id="sc-copy-sql")
                    with Vertical(classes="main"):
                        with Horizontal(id="viewbar"):
                            yield Button("Tables", id="sv-cards", variant="primary", compact=True)
                            yield Button("Foreign keys", id="sv-fks", compact=True)
                            yield Button("SQL DDL", id="sv-sql", compact=True)
                        with ContentSwitcher(initial="sc-cards", id="sc-views"):
                            with VerticalScroll(id="sc-cards", classes="scroll"):
                                yield Static(id="sc-cards-body")
                            with VerticalScroll(id="sc-fks", classes="scroll"):
                                yield Static(id="sc-fks-body")
                            with VerticalScroll(id="sc-sql", classes="scroll"):
                                yield Static(id="sc-sql-body")

            # ---- 3. query lab ----------------------------------------------------
            with TabPane("③ Query Lab", id="lab"):
                with Horizontal():
                    with Vertical(classes="side", id="lab-side"):
                        yield Label("DATABASE", classes="h first")
                        yield Input(placeholder="a.json; b.json   (; separates files)", id="db-path")
                        with Horizontal(classes="row"):
                            yield Button("Browse…", id="db-browse")
                            yield Button("Load", id="db-load", variant="primary")
                        yield Label("TABLES", classes="h")
                        yield Tree("database", id="db-tree")
                        yield Label("HISTORY & EXAMPLES", classes="h")
                        yield OptionList(id="snippets")
                    with Vertical(classes="main"):
                        yield QueryEditor(id="editor")
                        yield Static(id="ribbon")
                        with Horizontal(id="toolbar"):
                            yield Button("▶ Run", id="run", variant="success", compact=True)
                            yield Button("Clear", id="clear", compact=True)
                            yield Button("Export CSV", id="csv", compact=True)
                            yield Button("? Syntax", id="help-btn", compact=True)
                            yield Static(id="livechip")
                        with Horizontal(id="results"):
                            with Vertical(id="grid-wrap"):
                                yield DataTable(id="grid", zebra_stripes=True, cursor_type="row")
                            with Vertical(id="plan-wrap"):
                                yield Tree("plan", id="plan")
        yield Footer()

    # -------------------------------------------------------------- lifecycle --
    def on_mount(self) -> None:
        self.register_theme(THEME)
        self.theme = "schemagram"
        editor = self.query_one("#editor", QueryEditor)
        editor.register_theme(EDITOR_THEME)
        editor.theme = "schemagram"
        self.query_one("#grid", DataTable).show_row_labels = True
        self.query_one("#grid-wrap").border_title = "RESULT"
        self.query_one("#plan-wrap").border_title = "EXECUTION PLAN"
        self.query_one("#plan", Tree).show_root = False
        self.query_one("#db-tree", Tree).show_root = False
        self.query_one("#db-tree", Tree).root.expand()

        logo = Text()
        logo.append_text(gradient("◆ S C H E M A G R A M", P["cyan"], P["violet"]))
        logo.append("\n")
        logo.append("ER diagram  →  relational schema  →  relational algebra", style=P["dim"])
        self.query_one("#logo", Static).update(logo)

        self._load_examples()
        self._rebuild_samples()
        self._refresh_live_chip()
        self._refresh_all()

        # demo project so the first screen is alive
        er = resolve("examples/university_er.json")
        if er:
            self.query_one("#er-path", Input).value = os.path.relpath(er) if er.is_relative_to(Path.cwd()) else str(er)
            self.load_er(er, quiet=True)
        parts = [resolve("examples/university_people.json"), resolve("examples/university_courses.json")]
        if all(parts):
            self.query_one("#db-path", Input).value = "; ".join(
                os.path.relpath(p) if p.is_relative_to(Path.cwd()) else str(p) for p in parts)
            self.load_db(parts, quiet=True)
            if self.database and {"Student", "Department"} <= set(self.database):
                editor.load_text(
                    "PROJECT([FirstName, DeptName, GPA],\n"
                    "  SELECT(GPA >= 3.5,\n"
                    "    JOIN(Student.Department_DeptID == Department.DeptID, Student, Department)))")
                self._analyze(run=True)

    def get_system_commands(self, screen):
        yield from super().get_system_commands(screen)
        yield SystemCommand("Show query syntax", "Operators, notation and key bindings", self.action_help)
        yield SystemCommand("Toggle live execution", "Re-run the query as you type", self.action_toggle_live)
        yield SystemCommand("Go to ER diagram", "", lambda: self.action_goto("er"))
        yield SystemCommand("Go to relational schema", "", lambda: self.action_goto("schema"))
        yield SystemCommand("Go to query lab", "", lambda: self.action_goto("lab"))
        yield SystemCommand("Export diagram as PNG", "Needs Graphviz", self.action_export)

    # ---------------------------------------------------------------- actions --
    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_goto(self, tab: str) -> None:
        self.query_one(TabbedContent).active = tab

    def action_toggle_live(self) -> None:
        self.live = not self.live
        self._refresh_live_chip()
        self.notify("Live execution " + ("on" if self.live else "off"), timeout=2)
        if self.live:
            self._analyze(run=True)

    def action_run(self) -> None:
        self.action_goto("lab")
        self._analyze(run=True, record=True)

    def action_export(self) -> None:
        tab = self.query_one(TabbedContent).active
        if tab == "schema":
            self._export_schema()
        elif tab == "er":
            self._export_er()
        else:
            self.notify("Switch to the ER or Schema tab to export a diagram.", severity="warning")

    @on(TabbedContent.TabActivated)
    def _tab_changed(self, event: TabbedContent.TabActivated) -> None:
        if event.pane.id == "lab":
            self.query_one("#editor").focus()

    # ------------------------------------------------------------ file loading --
    def _read_json(self, path: Path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def load_er(self, path: Path | str, quiet: bool = False) -> bool:
        p = resolve(str(path))
        try:
            if p is None:
                raise FileNotFoundError(f"no such file: {path}")
            data = self._read_json(p)
            if not isinstance(data, dict) or "entities" not in data:
                raise ValueError("this doesn't look like an ER JSON file (missing top-level 'entities')")
            erd = ERDiagram.fromDict(data)
        except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError, AttributeError) as exc:
            msg = f"missing key {exc}" if isinstance(exc, KeyError) else str(exc)
            self.notify(msg, title="Could not load ER file", severity="error")
            return False
        self.er_path, self.er_data, self.erd = p, data, erd
        self.er_issues = er_lint(erd)
        self.tables, self.map_error = [], None
        try:
            self.tables = mapERDiagram(erd)
        except (ValueError, KeyError, TypeError) as exc:
            self.map_error = f"missing entity {exc}" if isinstance(exc, KeyError) else str(exc)
        self._refresh_all()
        if not quiet:
            self.notify(f"{len(erd.entities)} entities · {len(erd.relationships)} relationships",
                        title=f"Loaded {p.name}", timeout=3)
            if self.map_error:
                self.notify(self.map_error, title="Schema mapping failed", severity="warning")
        return True

    def load_db(self, paths: list[Path], quiet: bool = False) -> bool:
        try:
            db = loadDatabases([str(p) for p in paths])
        except (OSError, json.JSONDecodeError, ValueError, TypeError, AttributeError) as exc:
            self.notify(str(exc), title="Could not load database", severity="error")
            return False
        self.database, self.db_paths = db, list(paths)
        self._rebuild_db_tree()
        self._rebuild_vocab()
        self._refresh_chips()
        self._refresh_schema()  # SQL types come from the data
        if not quiet:
            rows = sum(len(t.rows) for t in db.values())
            self.notify(f"{len(db)} tables · {rows} rows", title="Database loaded", timeout=3)
        self._analyze(run=bool(self.query_one("#editor", QueryEditor).text.strip()))
        return True

    # ------------------------------------------------------------- refreshing --
    def _refresh_all(self) -> None:
        self._refresh_er()
        self._refresh_schema()
        self._refresh_chips()

    def _refresh_chips(self) -> None:
        t = Text()
        if self.er_path:
            t.append("● ", style=P["green"])
            t.append(f"ER {self.er_path.name}", style=P["text"])
        else:
            t.append("○ ER —", style=P["dim"])
        t.append("   ")
        if self.database:
            rows = sum(len(r.rows) for r in self.database.values())
            t.append("● ", style=P["green"])
            t.append(f"DB {len(self.database)} tables · {rows} rows", style=P["text"])
        else:
            t.append("○ DB —", style=P["dim"])
        self.query_one("#chips", Static).update(t)

    def _refresh_er(self) -> None:
        view = self.query_one("#er-view", Static)
        stats = self.query_one("#er-stats", Static)
        if not self.erd:
            view.update(Panel(
                Text.assemble(("No ER diagram loaded.\n\n", f"bold {P['text']}"),
                              ("Pick a sample on the left, or load a JSON file that follows ", P["dim"]),
                              ("erdiagram/er_json_schema.md", P["cyan"]), (".", P["dim"])),
                border_style=P["line"], padding=(1, 2)))
            stats.update(Text("—", style=P["dim"]))
            return
        stats.update(er_stats(self.erd))

        def heading(label: str, n: int) -> Text:
            return Text.assemble((f"{label}  ", f"bold {P['cyan']}"), (str(n), P["dim"]))

        view.update(Group(
            ER_LEGEND, Text(""),
            heading("ENTITIES", len(self.erd.entities)), Text(""), er_cards(self.erd), Text(""),
            heading("RELATIONSHIPS", len(self.erd.relationships)), Text(""),
            er_relationships(self.erd), Text(""),
            lint_panel(self.er_issues),
        ))

    def _refresh_schema(self) -> None:
        cards = self.query_one("#sc-cards-body", Static)
        fks = self.query_one("#sc-fks-body", Static)
        sql = self.query_one("#sc-sql-body", Static)
        stats = self.query_one("#sc-stats", Static)
        src = self.query_one("#sc-source", Static)
        if not self.erd:
            empty = Panel(Text("Load an ER diagram first (tab ①).", style=P["dim"]),
                          border_style=P["line"], padding=(1, 2))
            for w in (cards, fks, sql):
                w.update(empty)
            stats.update(Text("—", style=P["dim"]))
            src.update(Text("—", style=P["dim"]))
            return
        src.update(Text(self.er_path.name if self.er_path else "—", style=f"bold {P['text']}"))
        if self.map_error:
            panel = Panel(
                Text.assemble(("The ER diagram can't be mapped yet\n\n", f"bold {P['pink']}"),
                              (self.map_error, P["text"])),
                border_style=P["pink"], padding=(1, 2))
            for w in (cards, fks, sql):
                w.update(panel)
            stats.update(Text("mapping failed", style=P["pink"]))
            return
        stats.update(schema_stats(self.tables))
        cards.update(schema_cards(self.tables))
        fks.update(schema_fk_tree(self.tables))
        sql.update(Syntax(schema_sql(self.tables, self.database, self.er_path.name if self.er_path else ""),
                          "sql", theme="monokai", background_color=P["bg"], word_wrap=False))

    def _rebuild_samples(self) -> None:
        ol = self.query_one("#er-samples", OptionList)
        ol.clear_options()
        seen = set()
        for folder in (Path.cwd() / "examples", BASE / "examples"):
            if not folder.is_dir():
                continue
            for f in sorted(folder.glob("*.json")):
                if f.resolve() in seen:
                    continue
                try:
                    d = self._read_json(f)
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(d, dict) and "entities" in d:
                    seen.add(f.resolve())
                    ol.add_option(Option(Text.assemble(("◆ ", P["gold"]), (f.name, P["text"])), id=str(f)))
        if not seen:
            ol.add_option(Option(Text("no samples found", style=P["dim"]), disabled=True))

    # -------------------------------------------------------------- query lab --
    def _load_examples(self) -> None:
        out: list[str] = []
        for folder in (Path.cwd() / "examples", BASE / "examples"):
            if not folder.is_dir():
                continue
            for f in sorted(folder.glob("*.rql")):
                buf: list[str] = []
                for raw in f.read_text(encoding="utf-8").splitlines() + [""]:
                    line = raw.rstrip()
                    if line.lstrip().startswith(("--", "#", "//")):
                        continue
                    if not line.strip():
                        if buf:
                            out.append("\n".join(buf))
                            buf = []
                        continue
                    buf.append(line)
                    try:
                        Parser(Lexer("\n".join(buf)).tokenize()).parse()
                    except Exception:
                        if len(buf) > 12:
                            out.append("\n".join(buf))
                            buf = []
                        continue
                    out.append("\n".join(buf))
                    buf = []
            if out:
                break
        self.examples = list(dict.fromkeys(out))

    def _vocab(self) -> dict[str, list[str]]:
        if not self.database:
            return {}
        return {name: [c.columnName for c in res.columns] for name, res in self.database.items()}

    def _rebuild_vocab(self) -> None:
        self.query_one("#editor", QueryEditor).set_vocab(self._vocab())
        if not self.examples and self.database:
            first = next(iter(self.database))
            cols = [c.columnName for c in self.database[first].columns]
            self.examples = [first]
            if cols:
                self.examples += [f"PROJECT([{cols[0]}], {first})", f"AGGREGATE(COUNT, {cols[0]}, {first})"]
        self._rebuild_snippets()

    def _rebuild_snippets(self) -> None:
        ol = self.query_one("#snippets", OptionList)
        ol.clear_options()
        self._snippet_map = {}
        vocab = self._vocab()

        def prompt(q: str) -> Text:
            one = re.sub(r"\s+", " ", q).strip()
            t = Text(one if len(one) <= 31 else one[:30] + "…", no_wrap=True)
            highlight_line(t, t.plain, vocab)
            return t

        def section(label: str) -> Option:
            return Option(Text(label, style=f"bold {P['dim']}"), disabled=True)

        if self.history:
            ol.add_option(section("RECENT"))
            for i, q in enumerate(self.history):
                key = f"h{i}"
                self._snippet_map[key] = q
                ol.add_option(Option(prompt(q), id=key))
        if self.examples:
            ol.add_option(section("EXAMPLES"))
            for i, q in enumerate(self.examples):
                key = f"e{i}"
                self._snippet_map[key] = q
                ol.add_option(Option(prompt(q), id=key))

    def _rebuild_db_tree(self) -> None:
        tree = self.query_one("#db-tree", Tree)
        tree.clear()
        if not self.database:
            return
        for name, res in self.database.items():
            label = Text.assemble(("▤ ", P["teal"]), (name, f"bold {P['teal']}"),
                                  (f"  {len(res.rows)}×{len(res.columns)}", P["dim"]))
            node = tree.root.add(label, data=("table", name), expand=False)
            for i, c in enumerate(res.columns):
                kind = column_kind([r[i] for r in res.rows])
                node.add_leaf(Text.assemble(("· ", P["dim"]), (c.columnName, P["cyan"]), (f"  {kind}", P["dim"])),
                              data=("col", name, c.columnName))
        tree.root.expand()

    def _refresh_live_chip(self) -> None:
        chip = Text.assemble(("● live " if self.live else "○ live ", P["green"] if self.live else P["dim"]),
                             ("Ctrl+L", P["dim"]))
        self.query_one("#livechip", Static).update(chip)

    # ---- analysis / execution -----------------------------------------------------
    def _set_ribbon(self, *parts) -> None:
        self.query_one("#ribbon", Static).update(Group(*parts))

    def _analyze(self, run: bool = False, record: bool = False) -> None:
        editor = self.query_one("#editor", QueryEditor)
        source = editor.text
        self.ast = None
        if not source.strip():
            self._set_ribbon(Text("Relational algebra, written as nested calls. Press F1 for the syntax, "
                                  "Tab to complete names, F5 to run.", style=f"italic {P['dim']}"))
            self._clear_results()
            return
        try:
            self.ast = Parser(Lexer(source).tokenize()).parse()
        except Exception as exc:
            self._set_ribbon(explain_error(source, exc))
            return
        n_ops = count_operators(self.ast)
        info = Text.assemble(
            ("✓ ", f"bold {P['green']}"), (f"{n_ops} operator{'s' if n_ops != 1 else ''}", P["text"]),
            ("  ·  uses ", P["dim"]), (", ".join(relations_used(self.ast)), P["teal"]),
        )
        if self._ribbon_hint:
            info.append("\ncompletions: ", style=P["dim"])
            info.append("  ".join(self._ribbon_hint[:12]) + (" …" if len(self._ribbon_hint) > 12 else ""),
                        style=P["gold"])
        formal_line = Text.assemble(("≡ ", f"bold {P['violet']}"))
        formal_line.append_text(formal(self.ast))
        self._set_ribbon(formal_line, info)
        if run:
            self._execute(record=record)

    def _execute(self, record: bool = False) -> None:
        if self.ast is None:
            return
        if not self.database:
            self.notify("Load a database first (left panel).", severity="warning")
            return
        trace = run_trace(self.database, self.ast)
        self._show_plan(trace)
        err = trace.first_error()
        if err is not None:
            self._set_ribbon(
                Text.assemble(("≡ ", f"bold {P['violet']}")).append_text(formal(self.ast)),
                Text.assemble(("✗ ", f"bold {P['pink']}"), (err.error or "", f"bold {P['pink']}")),
            )
            self.last_result = None
            self._clear_results(keep_plan=True, message=err.error or "error")
            return
        if trace.result is not None:
            self._show_result(trace.result, "RESULT", trace)
            if record:
                src = self.query_one("#editor", QueryEditor).text.strip()
                if src in self.history:
                    self.history.remove(src)
                self.history.insert(0, src)
                del self.history[20:]
                self._rebuild_snippets()

    def _clear_results(self, keep_plan: bool = False, message: str | None = None) -> None:
        grid = self.query_one("#grid", DataTable)
        grid.clear(columns=True)
        wrap = self.query_one("#grid-wrap")
        wrap.border_title = "RESULT"
        wrap.border_subtitle = message or ""
        self.last_result = None
        if not keep_plan:
            self.query_one("#plan", Tree).clear()

    def _show_plan(self, trace: TraceNode) -> None:
        tree = self.query_one("#plan", Tree)
        tree.clear()

        def add(parent, tn: TraceNode) -> None:
            if tn.children:
                node = parent.add(trace_label(tn), data=tn, expand=True)
                for k in tn.children:
                    add(node, k)
            else:
                parent.add_leaf(trace_label(tn), data=tn)

        add(tree.root, trace)
        tree.root.expand()

    def _show_result(self, result: Result, title: str, trace: TraceNode | None = None) -> None:
        grid = self.query_one("#grid", DataTable)
        grid.clear(columns=True)
        flags = numeric_columns(result)
        for i, c in enumerate(result.columns):
            grid.add_column(column_header(c, flags[i]), key=f"c{i}")
        for n, row in enumerate(result.rows[:MAX_ROWS], 1):
            grid.add_row(*[cell_text(v, flags[i]) for i, v in enumerate(row)], label=Text(str(n), style=P["dim"]))
        wrap = self.query_one("#grid-wrap")
        wrap.border_title = title
        sub = f"{len(result.rows)} row{'s' if len(result.rows) != 1 else ''} × {len(result.columns)} col{'s' if len(result.columns) != 1 else ''}"
        if trace is not None and trace.ms:
            sub += f" · {trace.ms:.2f} ms"
        if len(result.rows) > MAX_ROWS:
            sub += f" · showing first {MAX_ROWS}"
        wrap.border_subtitle = sub
        self.last_result = result

    # ------------------------------------------------------------------ events --
    @on(TextArea.Changed, "#editor")
    def _editor_changed(self, event: TextArea.Changed) -> None:
        self._ribbon_hint = []  # a completion's Hint message is processed right after this
        self._analyze(run=False)
        if self._live_timer is not None:
            self._live_timer.stop()
            self._live_timer = None
        if self.live and self.ast is not None and self.database:
            self._live_timer = self.set_timer(0.25, lambda: self._execute(record=False))

    @on(QueryEditor.Hint)
    def _editor_hint(self, event: QueryEditor.Hint) -> None:
        self._ribbon_hint = event.candidates
        self._analyze(run=False)

    @on(Button.Pressed)
    def _button(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "er-load":
            self.load_er(self.query_one("#er-path", Input).value.strip())
        elif bid == "er-browse":
            self._browse("Choose an ER JSON file", self.query_one("#er-path", Input),
                         lambda p: self.load_er(p), append=False)
        elif bid == "er-export":
            self._export_er()
        elif bid == "sc-export":
            self._export_schema()
        elif bid == "sc-save-sql":
            self._save_sql()
        elif bid == "sc-copy-sql":
            if self.tables:
                self.copy_to_clipboard(schema_sql(self.tables, self.database,
                                                  self.er_path.name if self.er_path else ""))
                self.notify("SQL copied to clipboard", timeout=2)
            else:
                self.notify("Nothing to copy — load an ER diagram first.", severity="warning")
        elif bid in ("sv-cards", "sv-fks", "sv-sql"):
            self.query_one("#sc-views", ContentSwitcher).current = "sc-" + bid.removeprefix("sv-")
            for b in ("sv-cards", "sv-fks", "sv-sql"):
                self.query_one(f"#{b}", Button).variant = "primary" if b == bid else "default"
        elif bid == "db-load":
            self._load_db_from_input()
        elif bid == "db-browse":
            inp = self.query_one("#db-path", Input)
            self._browse("Add a database JSON file", inp, None, append=True)
        elif bid == "run":
            self.action_run()
        elif bid == "clear":
            ed = self.query_one("#editor", QueryEditor)
            ed.load_text("")
            ed.focus()
        elif bid == "csv":
            self._export_csv()
        elif bid == "help-btn":
            self.action_help()

    @on(Input.Submitted)
    def _submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "er-path":
            self.load_er(event.value.strip())
        elif event.input.id == "db-path":
            self._load_db_from_input()

    @on(OptionList.OptionSelected, "#er-samples")
    def _sample_chosen(self, event: OptionList.OptionSelected) -> None:
        if event.option.id:
            self.query_one("#er-path", Input).value = event.option.id
            self.load_er(event.option.id)

    @on(OptionList.OptionSelected, "#snippets")
    def _snippet_chosen(self, event: OptionList.OptionSelected) -> None:
        q = self._snippet_map.get(event.option.id or "")
        if q is not None:
            ed = self.query_one("#editor", QueryEditor)
            ed.load_text(q)
            ed.move_cursor(ed.document.end)
            ed.focus()

    @on(Tree.NodeSelected, "#db-tree")
    def _db_node(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if not data or not self.database:
            return
        ed = self.query_one("#editor", QueryEditor)
        if data[0] == "table":
            self._show_result(self.database[data[1]], f"TABLE · {data[1]}")
            if not ed.text.strip():
                ed.load_text(data[1])
        elif data[0] == "col":
            ed.insert(data[2])
            ed.focus()

    @on(Tree.NodeHighlighted, "#plan")
    def _plan_node(self, event: Tree.NodeHighlighted) -> None:
        tn = event.node.data
        if isinstance(tn, TraceNode) and tn.result is not None:
            n = tn.node
            title = f"▤ {n.name}" if isinstance(n, Relation) else f"{operator_symbol(n)} {OP_NAME[type(n)]}"
            self._show_result(tn.result, title, tn)

    def _load_db_from_input(self) -> None:
        raw = self.query_one("#db-path", Input).value
        names = [s.strip() for s in re.split(r"[;\n]", raw) if s.strip()]
        if not names:
            self.notify("Enter at least one database JSON file.", severity="warning")
            return
        paths = []
        for n in names:
            p = resolve(n)
            if p is None:
                self.notify(f"no such file: {n}", title="Could not load database", severity="error")
                return
            paths.append(p)
        self.load_db(paths)

    def _browse(self, title: str, target: Input, then, append: bool) -> None:
        def done(path: Path | None) -> None:
            if path is None:
                return
            shown = os.path.relpath(path) if path.is_relative_to(Path.cwd()) else str(path)
            if append and target.value.strip():
                target.value = target.value.rstrip("; ") + "; " + shown
            else:
                target.value = shown
            if then:
                then(path)
            elif append:
                self._load_db_from_input()

        start = Path.cwd()
        self.push_screen(FilePicker(title, start), done)

    # ------------------------------------------------------------------ exports --
    def _export_er(self) -> None:
        if not self.erd or self.er_data is None:
            self.notify("Load an ER diagram first.", severity="warning")
            return
        errors = [m for lvl, m in self.er_issues if lvl == "error"]
        if errors:
            self.notify(errors[0], title="Fix the ER file before exporting", severity="error")
            return
        self.notify("Rendering with Graphviz…", timeout=2)
        self._render_worker("er", self.query_one("#er-out", Input).value.strip() or "out/er_diagram")

    def _export_schema(self) -> None:
        if not self.erd or self.map_error:
            self.notify(self.map_error or "Load an ER diagram first.", severity="warning")
            return
        self.notify("Rendering with Graphviz…", timeout=2)
        self._render_worker("schema", self.query_one("#sc-out", Input).value.strip() or "out/relational_schema")

    @work(thread=True, exclusive=True, group="render")
    def _render_worker(self, kind: str, out: str) -> None:
        try:
            if kind == "er":
                path = renderERDiagram(self.er_data, out)
            else:
                path, _ = renderRelationalSchema(self.er_data, out)
        except Exception as exc:  # graphviz missing, bad path, ...
            hint = " Is Graphviz installed (the `dot` command)?" if "xecutable" in f"{type(exc).__name__}{exc}" else ""
            self.call_from_thread(self.notify, f"{exc}{hint}", title="Export failed", severity="error", timeout=8)
        else:
            self.call_from_thread(self.notify, str(path), title="PNG written", timeout=6)

    def _save_sql(self) -> None:
        if not self.tables:
            self.notify("Nothing to save — load an ER diagram first.", severity="warning")
            return
        out = Path(self.query_one("#sc-out", Input).value.strip() or "out/relational_schema").with_suffix(".sql")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(schema_sql(self.tables, self.database, self.er_path.name if self.er_path else ""),
                       encoding="utf-8")
        self.notify(str(out), title="SQL written", timeout=5)

    def _export_csv(self) -> None:
        if self.last_result is None:
            self.notify("Run a query first.", severity="warning")
            return
        out = Path("out/result.csv")
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([c.columnName for c in self.last_result.columns])
            w.writerows(["" if v is None else v for v in row] for row in self.last_result.rows)
        self.notify(f"{len(self.last_result.rows)} rows → {out}", title="CSV written", timeout=5)


def main() -> None:
    SchemagramApp().run()


if __name__ == "__main__":
    main()
