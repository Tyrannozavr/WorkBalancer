from workbalancer.presentation.web import routes as routes_mod


def test_parse_payload_maps_nested_fields() -> None:
    data = {
        "event": "statusChange",
        "id": "bc_abc",
        "status": "FINISHED",
        "summary": "s",
        "source": {"repository": "https://github.com/o/r", "ref": "main"},
        "target": {"url": "https://u", "branchName": "b", "prUrl": "https://pr"},
    }
    p = routes_mod._parse_payload(data)
    assert p.agent_id == "bc_abc"
    assert p.status == "FINISHED"
    assert p.repository == "https://github.com/o/r"
    assert p.pr_url == "https://pr"
