import json
from queryexecutor.classes import Column, Result

Database = dict[str, Result]

def loadDatabase(filePath: str) -> Database:
    with open(filePath) as f:
        data = json.load(f)

    db: Database = {}
    for tableName, records in data.items():
        # union of keys across ALL records, in first-seen order
        names = list(dict.fromkeys(k for r in records for k in r))

        for r in records:
            for k, v in r.items():
                if isinstance(v, (list, dict)):
                    raise ValueError(
                        f"{tableName}.{k}: nested values are not supported"
                    )

        db[tableName] = Result(
            columns=[Column(n, tableName) for n in names],
            rows=list(dict.fromkeys(tuple(r.get(n) for n in names) for r in records)),
        )
    return db


def loadDatabases(filePaths: list[str]) -> Database:
    """Load and merge several JSON files; a table name may appear only once."""
    db: Database = {}
    for filePath in filePaths:
        for name, table in loadDatabase(filePath).items():
            if name in db:
                raise ValueError(f"Table '{name}' (from {filePath}) is defined more than once")
            db[name] = table
    return db
