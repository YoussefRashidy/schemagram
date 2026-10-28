import json

from relationalvisualizer.classes import DataBase, TableSchema, Column, Table


def loadDataBase(filePath : str):
    with open(filePath) as json_file:
        data = json.load(json_file)

    tables : dict[str, Table] = {}
    for tableName , rows in data.items():
        columns = list(rows[0].keys())
        schema = TableSchema(tableName, columns = [Column(columnName) for columnName in columns])
        tables[tableName] = Table(schema,rows)
    return DataBase(tables)