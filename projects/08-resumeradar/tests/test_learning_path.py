import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resumeradar import ontology  # noqa: E402
from resumeradar.gaps import CycleError, learning_path, topological_sort  # noqa: E402


class TopoSortTest(unittest.TestCase):
    def test_prerequisites_come_first(self):
        pre = {"c": ["b"], "b": ["a"], "d": ["a"]}
        order = topological_sort(["d", "c", "b", "a"], pre)
        for node, reqs in pre.items():
            for r in reqs:
                self.assertLess(order.index(r), order.index(node))

    def test_deterministic_tie_break(self):
        pre = {"x": [], "y": [], "z": []}
        self.assertEqual(topological_sort(["z", "y", "x"], pre), ["x", "y", "z"])
        prio = {"x": 3, "y": 1, "z": 2}
        self.assertEqual(topological_sort(["x", "y", "z"], pre, priority=lambda n: prio[n]), ["y", "z", "x"])

    def test_edges_outside_node_set_are_ignored(self):
        self.assertEqual(topological_sort(["b"], {"b": ["a"]}), ["b"])

    def test_cycle_detected(self):
        with self.assertRaises(CycleError):
            topological_sort(["a", "b", "c"], {"a": ["c"], "b": ["a"], "c": ["b"]})

    def test_whole_ontology_is_acyclic(self):
        ids = list(ontology.SKILLS)
        order = topological_sort(ids, {s: ontology.get(s).prereqs for s in ids})
        self.assertEqual(len(order), len(ids))


class LearningPathTest(unittest.TestCase):
    def names(self, path):
        return [s["name"] for s in path["steps"]]

    def test_missing_prereqs_are_added_in_order(self):
        p = learning_path(["kubernetes"], known=set(), must_ids=["kubernetes"])
        n = self.names(p)
        self.assertEqual(n, ["Linux", "Docker", "Kubernetes"])
        self.assertEqual(p["steps"][0]["why"], "prerequisite for Docker")
        self.assertEqual(p["total_hours"], sum(ontology.get(s["id"]).hours for s in p["steps"]))

    def test_known_and_implied_skills_are_skipped(self):
        # Django implies Python, so Python is not re-taught before Django REST Framework
        p = learning_path(["django-rest-framework"], known={"django"}, must_ids=["django-rest-framework"])
        n = self.names(p)
        self.assertNotIn("Python", n)
        self.assertNotIn("Django", n)
        self.assertEqual(n[-1], "Django REST Framework")
        self.assertIn("REST APIs", n)
        self.assertLess(n.index("HTTP"), n.index("REST APIs"))

    def test_target_already_known_gives_empty_plan(self):
        p = learning_path(["python"], known={"python"})
        self.assertEqual(p["steps"], [])
        self.assertEqual(p["weeks"], 0)

    def test_must_haves_before_nice_to_haves(self):
        p = learning_path(["aws", "pytest"], known={"python"}, must_ids=["pytest"])
        n = self.names(p)
        self.assertLess(n.index("PyTest"), n.index("AWS"))

    def test_weeks_follow_hours(self):
        p = learning_path(["tableau"], known=set())
        self.assertEqual(self.names(p), ["Data Visualization", "Tableau"])
        self.assertEqual(p["steps"][-1]["week"], 5)   # 15 h + 20 h at 8 h/week -> week 5


if __name__ == "__main__":
    unittest.main()
