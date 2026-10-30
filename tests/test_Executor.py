"""Tests for the relational-algebra executor.

Invariant under test: every Result is a SET of rows (no duplicate rows).
  - established by the loader,
  - re-established by PROJECT and UNION (the only operators that can create
    duplicates),
  - preserved by every other operator.

Run with:  python -m unittest -v test_executor
"""
import json
import os
import random
import tempfile
import unittest

from queryexecutor.ASTNodes import (
    Relation, Select, Project, Join, Union, Intersect, Difference, Aggregate,
    Comparison, And, Or, ColumnRef, Literal,
)
from queryexecutor.classes import Column, Result
from queryexecutor.Executor import Executor
from queryexecutor.loader import loadDatabase      # <- adjust to wherever your loader lives


# --------------------------------------------------------------------------- #
# Tiny AST-building helpers
# --------------------------------------------------------------------------- #
def C(name, table=None):
    return ColumnRef(name, table)


def L(value):
    return Literal(value)


def R(name):
    return Relation(name)


def cmp(left, op, right):
    return Comparison(left, op, right)


def names(result):
    return [c.columnName for c in result.columns]


DATA = {
    "Students": [
        {"id": 1, "name": "Sara", "age": 22},
        {"id": 2, "name": "Omar", "age": 19},
        {"id": 3, "name": "Lina", "age": None},
        {"id": 4, "name": "Sara", "age": 25},
        {"id": 1, "name": "Sara", "age": 22},      # exact duplicate record
    ],
    "Enrolled": [
        {"sid": 1, "course": "CS"},
        {"sid": 2, "course": "EE"},
        {"sid": 1, "course": "EE"},
    ],
    "Alumni": [                                     # union-compatible with Students
        {"id": 2, "name": "Omar", "age": 19},
        {"id": 9, "name": "Zed", "age": 40},
    ],
    "Empty": [],
}

# What Students looks like once the loader has enforced the invariant.
STUDENTS = [(1, "Sara", 22), (2, "Omar", 19), (3, "Lina", None), (4, "Sara", 25)]


# --------------------------------------------------------------------------- #
# Loader
# --------------------------------------------------------------------------- #
class LoaderTests(unittest.TestCase):
    def load(self, data):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "db.json")
            with open(path, "w") as f:
                json.dump(data, f)
            return loadDatabase(path)

    def test_duplicate_records_are_collapsed(self):
        db = self.load(DATA)
        self.assertEqual(db["Students"].rows, STUDENTS)

    def test_columns_are_union_of_keys_with_none_fill(self):
        t = self.load({"t": [{"a": 1}, {"a": 2, "b": 3}]})["t"]
        self.assertEqual(names(t), ["a", "b"])
        self.assertEqual(t.rows, [(1, None), (2, 3)])

    def test_qualifier_is_table_name(self):
        t = self.load({"t": [{"a": 1, "b": 2}]})["t"]
        self.assertEqual(t.columns, [Column("a", "t"), Column("b", "t")])

    def test_empty_table(self):
        t = self.load({"t": []})["t"]
        self.assertEqual((t.columns, t.rows), ([], []))

    def test_nested_values_are_rejected(self):
        with self.assertRaises(ValueError):
            self.load({"t": [{"a": [1, 2]}]})
        with self.assertRaises(ValueError):
            self.load({"t": [{"a": {"x": 1}}]})


# --------------------------------------------------------------------------- #
# Executor
# --------------------------------------------------------------------------- #
class ExecutorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(cls.tmp.name, "db.json")
        with open(path, "w") as f:
            json.dump(DATA, f)
        cls.db = loadDatabase(path)
        cls.ex = Executor(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_query(self, ast):
        """Execute and check the invariant on EVERY result we ever look at."""
        result = self.ex.execute(ast)
        self.assertEqual(len(result.rows), len(set(result.rows)),
                         f"duplicate rows in result: {result.rows}")
        width = len(result.columns)
        for row in result.rows:
            self.assertEqual(len(row), width, f"row {row} does not match schema")
        return result

    # ---- relation -------------------------------------------------------- #
    def test_relation_returns_base_table(self):
        r = self.run_query(R("Students"))
        self.assertEqual(r.rows, STUDENTS)
        self.assertEqual(names(r), ["id", "name", "age"])

    def test_unknown_relation(self):
        with self.assertRaises(NameError):
            self.run_query(R("Nope"))

    def test_unknown_node(self):
        with self.assertRaises(TypeError):
            self.ex.execute("garbage")

    # ---- select ---------------------------------------------------------- #
    def test_select_comparison_drops_null_rows(self):
        r = self.run_query(Select(cmp(C("age"), ">", L(20)), R("Students")))
        self.assertEqual(r.rows, [(1, "Sara", 22), (4, "Sara", 25)])

    def test_select_not_equal(self):
        r = self.run_query(Select(cmp(C("name"), "!=", L("Sara")), R("Students")))
        self.assertEqual([row[0] for row in r.rows], [2, 3])

    def test_select_le_ge(self):
        cond = And(cmp(C("age"), ">=", L(22)), cmp(C("age"), "<=", L(22)))
        r = self.run_query(Select(cond, R("Students")))
        self.assertEqual(r.rows, [(1, "Sara", 22)])

    def test_select_and_or(self):
        cond = Or(And(cmp(C("age"), ">", L(20)), cmp(C("name"), "=", L("Sara"))),
                  cmp(C("id"), "=", L(2)))
        r = self.run_query(Select(cond, R("Students")))
        self.assertEqual([row[0] for row in r.rows], [1, 2, 4])

    def test_select_null_equals_null_is_never_true(self):
        r = self.run_query(Select(cmp(C("age"), "=", C("age")), R("Students")))
        self.assertEqual([row[0] for row in r.rows], [1, 2, 4])   # Lina (NULL) dropped

    def test_select_unknown_column(self):
        with self.assertRaises(NameError):
            self.run_query(Select(cmp(C("zzz"), "=", L(1)), R("Students")))

    def test_select_incomparable_types(self):
        with self.assertRaises(TypeError):
            self.run_query(Select(cmp(C("age"), ">", L("x")), R("Students")))

    # ---- project --------------------------------------------------------- #
    def test_project_dedupes_in_first_seen_order(self):
        r = self.run_query(Project([C("name")], R("Students")))
        self.assertEqual(r.rows, [("Sara",), ("Omar",), ("Lina",)])

    def test_project_reorders_columns_and_keeps_qualifiers(self):
        r = self.run_query(Project([C("name"), C("id")], R("Students")))
        self.assertEqual(r.columns, [Column("name", "Students"), Column("id", "Students")])
        self.assertEqual(r.rows[0], ("Sara", 1))

    def test_project_qualified_reference(self):
        r = self.run_query(Project([C("id", "Students")], R("Students")))
        self.assertEqual(r.rows, [(1,), (2,), (3,), (4,)])

    def test_project_unknown_or_wrongly_qualified_column(self):
        with self.assertRaises(NameError):
            self.run_query(Project([C("zzz")], R("Students")))
        with self.assertRaises(NameError):
            self.run_query(Project([C("id", "Nope")], R("Students")))

    # ---- join ------------------------------------------------------------ #
    def test_join_on_equality(self):
        r = self.run_query(Join(cmp(C("id", "Students"), "=", C("sid", "Enrolled")),
                                R("Students"), R("Enrolled")))
        self.assertEqual(names(r), ["id", "name", "age", "sid", "course"])
        self.assertEqual(r.rows, [
            (1, "Sara", 22, 1, "CS"),
            (1, "Sara", 22, 1, "EE"),
            (2, "Omar", 19, 2, "EE"),
        ])

    def test_join_with_never_true_condition_keeps_schema(self):
        r = self.run_query(Join(cmp(L(1), "=", L(2)), R("Students"), R("Enrolled")))
        self.assertEqual(r.rows, [])
        self.assertEqual(len(r.columns), 5)

    def test_join_with_empty_relation(self):
        r = self.run_query(Join(cmp(C("id"), "=", L(1)), R("Students"), R("Empty")))
        self.assertEqual(r.rows, [])
        self.assertEqual(names(r), ["id", "name", "age"])

    def test_self_join_is_ambiguous_without_rename(self):
        with self.assertRaises(NameError):
            self.run_query(Join(cmp(C("id"), "=", C("id")), R("Students"), R("Students")))

    def test_join_then_project(self):
        join = Join(cmp(C("id"), "=", C("sid")), R("Students"), R("Enrolled"))
        r = self.run_query(Project([C("name"), C("course")], join))
        self.assertEqual(r.rows, [("Sara", "CS"), ("Sara", "EE"), ("Omar", "EE")])

    # ---- set operations -------------------------------------------------- #
    def test_union_dedupes_overlap_and_keeps_left_first_order(self):
        r = self.run_query(Union(R("Students"), R("Alumni")))
        self.assertEqual(r.rows, STUDENTS + [(9, "Zed", 40)])

    def test_intersect(self):
        r = self.run_query(Intersect(R("Students"), R("Alumni")))
        self.assertEqual(r.rows, [(2, "Omar", 19)])

    def test_difference_is_directional(self):
        r = self.run_query(Difference(R("Students"), R("Alumni")))
        self.assertEqual(r.rows, [(1, "Sara", 22), (3, "Lina", None), (4, "Sara", 25)])
        r = self.run_query(Difference(R("Alumni"), R("Students")))
        self.assertEqual(r.rows, [(9, "Zed", 40)])

    def test_set_operations_use_left_column_names(self):
        r = self.run_query(Intersect(Project([C("id")], R("Students")),
                                     Project([C("sid")], R("Enrolled"))))
        self.assertEqual(names(r), ["id"])
        self.assertEqual(r.rows, [(1,), (2,)])

    def test_set_operations_with_empty_operand(self):
        nothing = Select(cmp(C("id"), ">", L(99)), R("Students"))
        self.assertEqual(self.run_query(Intersect(R("Students"), nothing)).rows, [])
        self.assertEqual(self.run_query(Union(R("Students"), nothing)).rows, STUDENTS)
        self.assertEqual(self.run_query(Difference(R("Students"), nothing)).rows, STUDENTS)

    def test_set_operations_reject_arity_mismatch(self):
        for op in (Union, Intersect, Difference):
            with self.subTest(op=op.__name__):
                with self.assertRaises(TypeError):
                    self.run_query(op(R("Students"), R("Enrolled")))

    # ---- aggregate ------------------------------------------------------- #
    def test_aggregates_skip_nulls_and_see_deduplicated_rows(self):
        # ages are 22, 19, NULL, 25 once the duplicate record is gone
        expected = {"COUNT": 3, "SUM": 66, "AVG": 22.0, "MIN": 19, "MAX": 25}
        for fn, value in expected.items():
            with self.subTest(fn=fn):
                r = self.run_query(Aggregate(fn, C("age"), R("Students")))
                self.assertEqual(r.rows, [(value,)])

    def test_aggregate_result_shape(self):
        r = self.run_query(Aggregate("COUNT", C("age"), R("Students")))
        self.assertEqual(r.columns, [Column("COUNT(age)", None)])
        self.assertEqual(len(r.rows), 1)

    def test_aggregates_over_empty_input(self):
        nothing = Select(cmp(C("id"), ">", L(99)), R("Students"))
        expected = {"COUNT": 0, "SUM": 0, "AVG": None, "MIN": None, "MAX": None}
        for fn, value in expected.items():
            with self.subTest(fn=fn):
                r = self.run_query(Aggregate(fn, C("age"), nothing))
                self.assertEqual(r.rows, [(value,)])

    def test_aggregate_over_projection(self):
        r = self.run_query(Aggregate("COUNT", C("name"), Project([C("name")], R("Students"))))
        self.assertEqual(r.rows, [(3,)])           # distinct names, not 4

    def test_unknown_aggregate_function(self):
        with self.assertRaises(ValueError):
            self.run_query(Aggregate("MEDIAN", C("age"), R("Students")))

    # ---- composition / safety ------------------------------------------- #
    def test_nested_query(self):
        join = Join(cmp(C("id"), "=", C("sid")), R("Students"), R("Enrolled"))
        q = Project([C("name")], Select(cmp(C("age"), ">", L(20)), join))
        self.assertEqual(self.run_query(q).rows, [("Sara",)])

    def test_base_tables_are_never_mutated(self):
        snapshot = {k: (list(v.columns), list(v.rows)) for k, v in self.db.items()}
        join = Join(cmp(C("id"), "=", C("sid")), R("Students"), R("Enrolled"))
        for q in (R("Students"),
                  Select(cmp(C("id"), ">", L(1)), R("Students")),
                  Project([C("name")], R("Students")),
                  join,
                  Union(R("Students"), R("Alumni")),
                  Intersect(R("Students"), R("Alumni")),
                  Difference(R("Students"), R("Alumni")),
                  Aggregate("SUM", C("age"), R("Students"))):
            self.run_query(q)
        after = {k: (list(v.columns), list(v.rows)) for k, v in self.db.items()}
        self.assertEqual(snapshot, after)


# --------------------------------------------------------------------------- #
# Randomized check against Python's own sets
# --------------------------------------------------------------------------- #
class SetSemanticsProperties(unittest.TestCase):
    def test_random_relations_match_python_set_semantics(self):
        rng = random.Random(0)
        cols = [Column("x", "T"), Column("y", "T")]

        def rand_relation():
            rows = [(rng.randint(0, 4), rng.randint(0, 4)) for _ in range(rng.randint(0, 8))]
            return list(dict.fromkeys(rows))      # establish the invariant

        for _ in range(300):
            a, b = rand_relation(), rand_relation()
            ex = Executor({"A": Result(cols, a), "B": Result(cols, b)})
            sa, sb = set(a), set(b)
            cases = [
                (Union(R("A"), R("B")),      list(dict.fromkeys(a + b))),
                (Intersect(R("A"), R("B")),  [t for t in a if t in sb]),
                (Difference(R("A"), R("B")), [t for t in a if t not in sb]),
                (Project([C("x")], R("A")),  list(dict.fromkeys((t[0],) for t in a))),
                (Project([C("y"), C("x")], R("A")),
                                             list(dict.fromkeys((t[1], t[0]) for t in a))),
            ]
            for node, expected in cases:
                with self.subTest(node=type(node).__name__, a=a, b=b):
                    out = ex.execute(node)
                    self.assertEqual(out.rows, expected)
                    self.assertEqual(len(out.rows), len(set(out.rows)))
            self.assertEqual(set(ex.execute(Union(R("A"), R("B"))).rows), sa | sb)
            self.assertEqual(set(ex.execute(Intersect(R("A"), R("B"))).rows), sa & sb)
            self.assertEqual(set(ex.execute(Difference(R("A"), R("B"))).rows), sa - sb)


if __name__ == "__main__":
    unittest.main()