from backend.app.agents.tools import ZohoProjectsToolkit


def test_normalise_task_tolerates_unassigned_owner_without_id():
    task = {
        "id": 451058000000077022,
        "name": "API Integration",
        "description": "",
        "priority": "None",
        "percent_complete": "0",
        "tasklist": {"id": "451058000000075002", "name": "General"},
        "status": {"name": "Open"},
        "details": {
            "owners": [
                {
                    "name": "Unassigned",
                }
            ]
        },
    }

    result = ZohoProjectsToolkit._normalise_task(task)

    assert result["id"] == "451058000000077022"
    assert result["owners"] == [{"name": "Unassigned"}]