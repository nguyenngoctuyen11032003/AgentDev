from agentdev.api.services.workflow_diff import diff_workflows, unrequested_changes


def _doc(nodes, edges, **graph):
    return {"version": 1, "graph": {"id": "g", "nodes": nodes, "edges": edges, **graph}}


def _node(nid, **config):
    return {"id": nid, "type": "agent", "description": "", "config": config}


def test_diff_detects_added_removed_changed():
    old = _doc([_node("A", role="x"), _node("B")], [{"from": "A", "to": "B"}])
    new = _doc([_node("A", role="y"), _node("C")], [{"from": "A", "to": "C"}])
    d = diff_workflows(old, new)
    assert d["nodes_added"] == ["C"]
    assert d["nodes_removed"] == ["B"]
    assert d["nodes_changed"] == [{"id": "A", "fields": ["config.role"]}]
    assert d["edges_added"] == [{"from": "A", "to": "C"}]
    assert d["edges_removed"] == [{"from": "A", "to": "B"}]
    assert d["edges_changed"] == []
    assert d["graph_fields_changed"] == []


def test_diff_field_paths_are_leaf_level():
    old = _doc([_node("A", team={"members": ["a"], "max_delegations": 1, "k": 1})], [])
    new = _doc([_node("A", team={"members": ["a", "b"], "max_delegations": 2, "k": 1})], [])
    d = diff_workflows(old, new)
    assert d["nodes_changed"] == [
        {"id": "A", "fields": ["config.team.members", "config.team.max_delegations"]}
    ]


def test_diff_create_lists_all_nodes_added():
    new = _doc([_node("A"), _node("B")], [{"from": "A", "to": "B"}])
    d = diff_workflows(None, new)
    assert d["nodes_added"] == ["A", "B"]
    assert d["nodes_removed"] == []
    assert d["edges_added"] == [{"from": "A", "to": "B"}]


def test_diff_identical_is_empty():
    doc = _doc([_node("A")], [{"from": "A", "to": "A"}], start=["A"])
    d = diff_workflows(doc, doc)
    assert all(v == [] for v in d.values())


def test_diff_edge_attribute_and_graph_fields():
    old = _doc([_node("A"), _node("B")], [{"from": "A", "to": "B"}], start=["A"])
    new = _doc(
        [_node("A"), _node("B")],
        [{"from": "A", "to": "B", "condition": "ok"}],
        start=["B"],
    )
    d = diff_workflows(old, new)
    assert d["edges_changed"] == [{"from": "A", "to": "B", "fields": ["condition"]}]
    assert d["graph_fields_changed"] == ["start"]
    assert d["edges_added"] == [] and d["edges_removed"] == []


def test_unrequested_flags_unmentioned():
    diff = {
        "nodes_added": [], "nodes_removed": [], "edges_added": [], "edges_removed": [],
        "nodes_changed": [
            {"id": "Bug Fixer", "fields": ["config.role"]},
            {"id": "QA Tester", "fields": ["config.role"]},
        ],
    }
    assert unrequested_changes(diff, "sửa role của qa tester") == ["Bug Fixer"]


def test_unrequested_matches_underscore_and_dash_forms():
    diff = {"nodes_removed": ["bug_fixer", "qa-tester"], "nodes_changed": [], "edges_removed": []}
    assert unrequested_changes(diff, "xóa bug fixer và qa tester") == []


def test_unrequested_ignores_added_nodes():
    diff = {"nodes_added": ["Z"], "nodes_removed": [], "nodes_changed": [], "edges_removed": []}
    assert unrequested_changes(diff, "") == []


def test_unrequested_removed_edge():
    diff = {"nodes_removed": [], "nodes_changed": [], "edges_removed": [{"from": "A", "to": "B"}]}
    assert unrequested_changes(diff, "đổi tên") == ["A", "B"]
    assert unrequested_changes(diff, "bỏ cạnh từ a") == []


def test_diff_parallel_edges_are_distinct():
    nodes = [_node("A"), _node("B")]
    old = _doc(nodes, [{"from": "A", "to": "B"}, {"from": "A", "to": "B", "condition": "x"}])
    dropped = _doc(nodes, [{"from": "A", "to": "B"}])
    d = diff_workflows(old, dropped)
    assert d["edges_removed"] == [{"from": "A", "to": "B"}]
    assert d["edges_changed"] == []
    edited = _doc(nodes, [{"from": "A", "to": "B"}, {"from": "A", "to": "B", "condition": "y"}])
    d = diff_workflows(old, edited)
    assert d["edges_changed"] == [{"from": "A", "to": "B", "fields": ["condition"]}]
    assert d["edges_removed"] == [] and d["edges_added"] == []


def test_unrequested_normalises_unicode():
    import unicodedata
    diff = {"nodes_removed": [unicodedata.normalize("NFD", "Kiểm thử")], "nodes_changed": [], "edges_removed": []}
    assert unrequested_changes(diff, unicodedata.normalize("NFC", "xóa kiểm thử")) == []
