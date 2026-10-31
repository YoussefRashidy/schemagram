from __future__ import annotations

import json
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Label, RichLog, Static

from erdiagram.classes import ERDiagram
from queryexecutor.Executor import Executor
from queryexecutor.Lexer import Lexer
from queryexecutor.Parser import Parser
from queryexecutor.loader import loadDatabases
from schemagram_core import describeSchema, renderERDiagram, renderRelationalSchema


class SchemagramApp(App):
    """Terminal interface for ER, relational-schema, and query workflows."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #mode-bar {
        height: 3;
        align: center middle;
    }
    #mode-bar Button {
        margin: 0 1;
    }
    .mode {
        display: none;
        height: 1fr;
        padding: 1 2;
    }
    .mode.-active {
        display: block;
    }
    Input {
        margin: 1 0;
    }
    Button {
        width: 24;
    }
    RichLog {
        height: 1fr;
        border: round $accent;
        margin-top: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.database = None
        self.executor = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="mode-bar"):
            yield Button("ER visualization", id="mode-er", variant="primary")
            yield Button("Relational schema", id="mode-schema")
            yield Button("Query mode", id="mode-query")

        with Container(id="er-mode", classes="mode -active"):
            yield Label("ER JSON file")
            yield Input(placeholder="examples/university_er.json", id="er-input")
            yield Label("Output PNG path (without extension is also accepted)")
            yield Input(value="out/er_diagram", id="er-output")
            yield Button("Render ER diagram", id="render-er", variant="success")
            yield RichLog(id="er-log", markup=False)

        with Container(id="schema-mode", classes="mode"):
            yield Label("ER JSON file")
            yield Input(placeholder="examples/university_er.json", id="schema-input")
            yield Label("Output PNG path (without extension is also accepted)")
            yield Input(value="out/relational_schema", id="schema-output")
            yield Button("Render relational schema", id="render-schema", variant="success")
            yield RichLog(id="schema-log", markup=False)

        with Container(id="query-mode", classes="mode"):
            yield Label("Database JSON file(s), separated by semicolons")
            yield Input(placeholder="examples/university_people.json;examples/university_courses.json",
                        id="database-input")
            yield Button("Load database", id="load-database", variant="success")
            yield Input(placeholder="PROJECT([Name], Students)", id="query-input")
            yield Button("Execute query", id="execute-query")
            yield RichLog(id="query-log", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Schemagram"
        self._show_mode("er")

    def _show_mode(self, mode: str) -> None:
        for name in ("er", "schema", "query"):
            self.query_one(f"#{name}-mode").set_class(name == mode, "-active")
            self.query_one(f"#mode-{name}").variant = "primary" if name == mode else "default"

    def _log(self, widget_id: str, message: str) -> None:
        self.query_one(f"#{widget_id}", RichLog).write(message)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id in {"mode-er", "mode-schema", "mode-query"}:
            self._show_mode(button_id.removeprefix("mode-"))
        elif button_id == "render-er":
            self._render_er()
        elif button_id == "render-schema":
            self._render_schema()
        elif button_id == "load-database":
            self._load_database()
        elif button_id == "execute-query":
            self._execute_query()

    def _read_json(self, input_id: str) -> dict:
        path = self.query_one(f"#{input_id}", Input).value.strip()
        with open(path, encoding="utf-8") as file:
            return json.load(file)

    def _render_er(self) -> None:
        try:
            data = self._read_json("er-input")
            output = self.query_one("#er-output", Input).value.strip()
            path = renderERDiagram(data, output)
            self._log("er-log", f"ER diagram written to {path}")
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as error:
            self._log("er-log", f"Error: {error}")

    def _render_schema(self) -> None:
        try:
            data = self._read_json("schema-input")
            output = self.query_one("#schema-output", Input).value.strip()
            path, summary = renderRelationalSchema(data, output)
            self._log("schema-log", summary)
            self._log("schema-log", f"Relational schema written to {path}")
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as error:
            self._log("schema-log", f"Error: {error}")

    def _load_database(self) -> None:
        try:
            paths = [path.strip() for path in
                     self.query_one("#database-input", Input).value.split(";") if path.strip()]
            if not paths:
                raise ValueError("enter at least one database JSON file")
            self.database = loadDatabases(paths)
            self.executor = Executor(self.database)
            self._log("query-log", f"Loaded {len(self.database)} table(s): {', '.join(self.database)}")
        except (OSError, json.JSONDecodeError, ValueError) as error:
            self._log("query-log", f"Error: {error}")

    def _execute_query(self) -> None:
        try:
            if self.executor is None:
                raise ValueError("load a database before executing a query")
            query = self.query_one("#query-input", Input).value.strip()
            if not query:
                raise ValueError("enter a query")
            result = self.executor.execute(Parser(Lexer(query).tokenize()).parse())
            self._log("query-log", self._format_result(result))
        except (SyntaxError, NameError, TypeError, ValueError, ZeroDivisionError) as error:
            self._log("query-log", f"Error: {error}")

    @staticmethod
    def _format_result(result) -> str:
        headers = [column.columnName for column in result.columns]
        rows = [["NULL" if value is None else str(value) for value in row]
                for row in result.rows]
        if not headers:
            return f"(0 rows)"
        widths = [max([len(headers[index])] +
                       [len(row[index]) for row in rows])
                  for index in range(len(headers))]
        lines = [
            " | ".join(value.ljust(width) for value, width in zip(headers, widths)),
            "-+-".join("-" * width for width in widths),
        ]
        lines.extend(" | ".join(value.ljust(width) for value, width in zip(row, widths))
                     for row in rows)
        lines.append(f"({len(rows)} row{'s' if len(rows) != 1 else ''})")
        return "\n".join(lines)


def main() -> None:
    SchemagramApp().run()
