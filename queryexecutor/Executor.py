from typing import Any

from relationalvisualizer.classes import *
from ASTNodes import *
from loader import Database
from classes import *
import operator
class Executor:
    OPS = {
        "=": operator.eq,
        "!=": operator.ne,
        "<": operator.lt,
        ">": operator.gt,
        "<=": operator.le,
        ">=": operator.ge,
    }

    AGGREGATES = {
        "COUNT": len,
        "SUM": sum,
        "AVG": lambda v: sum(v) / len(v),
        "MIN": min,
        "MAX": max,
    }

    EMPTY_RESULT = {"COUNT": 0, "SUM": 0, "AVG": None, "MIN": None, "MAX": None}

    def resolveColumn(self , result: Result, ref: ColumnRef) -> int:
        matches = [
            i for i, c in enumerate(result.columns)
            if c.columnName == ref.name
               and (ref.table is None or c.qualifier == ref.table)
        ]
        label = f"{ref.table}.{ref.name}" if ref.table else ref.name
        if not matches:
            raise NameError(f"Unknown column {label}")
        if len(matches) > 1:
            raise NameError(f"Ambiguous column {label}; qualify it with a table name")
        return matches[0]

    def evalCondition(self, cond, result: Result, row: tuple) -> bool | None | Any:
        match cond:
            case Or(left, right):
                return (self.evalCondition(left, result, row)
                        or self.evalCondition(right, result, row))
            case And(left, right):
                return (self.evalCondition(left, result, row)
                        and self.evalCondition(right, result, row))
            case Comparison(left, op, right):
                l = self.evalOperand(left, result, row)
                r = self.evalOperand(right, result, row)
                if l is None or r is None:  # SQL-style: comparing with NULL is never true
                    return False
                try:
                    return self.OPS[op](l, r)
                except TypeError:
                    raise TypeError(f"Cannot compare {l!r} {op} {r!r}") from None
            case _:
                raise TypeError(f"Unknown condition node: {cond!r}")

    def evalOperand(self, operand, result: Result, row: tuple):
        match operand:
            case Literal(value):
                return value
            case ColumnRef():
                return row[self.resolveColumn(result, operand)]
            case _:
                raise TypeError(f"Unknown operand node: {operand!r}")


    def __init__(self, db: "Database"):
        self.db = db



    def execute(self , node : "Query" ):
        match node:
            case Relation():
                return self.execRelation(node)
            case Select():
                return self.execSelect(node)
            case Project():
                return self.execProject(node)
            case Join():
                return self.execJoin(node)
            case Union():
                return self.execUnion(node)
            case Intersect():
                return self.execIntersect(node)
            case Difference():
                return self.execDifference(node)
            case Aggregate():
                return self.execAggregate(node)
            case _:
                raise TypeError(f"Unknown node: {node}")

    def execRelation(self, node):
        relation = self.db.get(node.name)
        if relation is None:
            raise TypeError(f"Unknown Relation: {node.name}")
        return relation

    def execSelect(self, node):
        queryResult = self.execute(node.query)
        tuples = [t for t in queryResult.rows if self.evalCondition(node.condition,t)]
        return Result(queryResult.columns, tuples)


    def execProject(self, node):
        queryResult = self.execute(node.query)
        indices = [self.resolveColumn(queryResult, column) for column in node.columns]
        tuples = dict.fromkeys(tuple(t[i] for i in indices) for t in queryResult.rows)
        return Result([queryResult.columns[i] for i in indices], list(tuples))


    def execUnion(self, node):
        left , right = self.execute(node.left) , self.execute(node.right)
        return Result(left.columns, list(dict.fromkeys(left.rows + right.rows)))

    def execIntersect(self, node):
        left, right = self.execute(node.left), self.execute(node.right)
        rightSet = set(right.rows)
        return Result(left.columns , [row for row in left.rows if row in rightSet])

    def execJoin(self, node):
        left = self.execute(node.left)
        right = self.execute(node.right)
        jointTable = Result(left.columns+right.columns,[])
        for t1 in left.rows:
            for t2 in right.rows:
                row = t1+t2
                if self.evalCondition(node.cond,row):
                    jointTable.rows.append(row)
        return jointTable


    def execDifference(self, node):
        left, right = self.execute(node.left), self.execute(node.right)
        rightSet = set(right.rows)
        return Result(left.columns , [row for row in left.rows if row not in rightSet])

    def execAggregate(self, node):
        function = self.AGGREGATES[node.function]
        if function is None:
            raise ValueError(f"Unknown aggregate function {node.function}")
        queryResult = self.execute(node.query)
        columnIndex = self.resolveColumn(queryResult , node.column)
        values = [row[columnIndex] for row in queryResult.rows if row[columnIndex] is not None]
        value = function(values) if values else self.EMPTY_RESULT[node.function.upper()]
        return Result([Column(f"{node.function}({node.column.name})", None)], [(value,)])