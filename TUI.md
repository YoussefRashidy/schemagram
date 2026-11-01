# Schemagram TUI

    pip install -r requirements.txt     # textual + graphviz (PNG export also needs the Graphviz `dot` binary)
    python schemagram.py

Tabs: F2 ER diagram · F3 relational schema · F4 query lab. F1 = help, F5 = run, Tab = complete,
Ctrl+L = live execution, Ctrl+E = export PNG, Ctrl+P = command palette (themes).

Files: `tui.py` (app) and `tui_render.py` (pure Rich renderers, no Textual).
`schemagram_core.renderERDiagram` now also draws partial keys, multi-valued/derived attributes,
roles and total participation, matching `erdiagram/main.py`.
