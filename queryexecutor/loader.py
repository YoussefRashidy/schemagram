import json
from classes import Column, Result

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
            rows=[tuple(r.get(n) for n in names) for r in records],
        )
    return db