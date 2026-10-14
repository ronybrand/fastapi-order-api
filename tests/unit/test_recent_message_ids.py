from api.utils.recent_message_ids import RecentMessageIds


def test_remembers_added_ids():
    ids = RecentMessageIds(capacity=3)

    ids.add("a")

    assert "a" in ids
    assert "b" not in ids


def test_forgets_the_oldest_id_when_over_capacity():
    ids = RecentMessageIds(capacity=2)

    for value in ("a", "b", "c"):
        ids.add(value)

    assert "a" not in ids
    assert "b" in ids
    assert "c" in ids
