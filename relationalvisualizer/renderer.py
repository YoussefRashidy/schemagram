import html
import graphviz

from relationalvisualizer.classes import TableSchema, DBSchema


FONT = "Helvetica"
def renderSchema(schema: DBSchema , out : str):
    dot = graphviz.Digraph(graph_attr={"rankdir": "TB", "nodesep": "0.8", "ranksep": "1.1",
                    "dpi": "200", "pad": "0.4", "bgcolor": "white"},
        node_attr={"shape": "plaintext", "fontname": FONT, "fontsize": "14"},
        edge_attr={"color": "#2b4c7e", "penwidth": "1.6", "arrowsize": "1.0"},)

    def port(i):
        return f"c{i}"
    def renderTable(table: TableSchema):
        columns = [f'<TD BGCOLOR="#2b4c7e"><FONT COLOR="white"><B>{html.escape(table.name)}</B></FONT></TD>']
        for i, column in enumerate(table.columns):
            col_name = html.escape(column.name)
            bg = "white"
            if column.isPrimaryKey:
                col_name = f"<U>{col_name}</U>"
                bg = "#fff3c4"
            if column.isForeignKey:
                col_name = f"<I>{col_name}</I>"
                if not column.isPrimaryKey:
                    bg = "#dce9f7"
            columns.append(f"<TD PORT=\"{port(i)}\" BGCOLOR=\"{bg}\">{col_name}</TD>")
        return (f"""<
        <TABLE BORDER="1" CELLBORDER="1" CELLSPACING="0" CELLPADDING="9" COLOR="#555555">
            <TR>
                {''.join(columns)}
            </TR>
        </TABLE>
        >""")

    ports = {table.name : {column.name : port(i) for i , column in enumerate(table.columns)} for table in schema.tables}
    for table in schema.tables:
        dot.node(table.name, renderTable(table))
    for table in schema.tables:
        for fk in table.foreignKeys:
            for col , ref in zip(fk.columns, fk.refColumns):
                if table.name == fk.refTable:
                    fromDirection , toDirection = "s" , "s"
                else:
                    fromDirection , toDirection = "s" , "n"
                dot.edge(f"{table.name}:{ports[table.name][col]}:{fromDirection}" , f"{fk.refTable}:{ports[fk.refTable][ref]}:{toDirection}")
    dot.render(out , format="png", cleanup=True)
