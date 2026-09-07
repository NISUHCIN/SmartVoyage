from backend.trace_store import clear_traces, list_traces, record_trace


def setup_function():
    clear_traces()


def test_record_trace_lists_newest_first():
    first = record_trace(
        kind="chat",
        message="第一条",
        session_id="s-1",
        agents=["WeatherQueryAssistant"],
        duration_ms=12,
    )
    second = record_trace(
        kind="chat",
        message="第二条",
        session_id="s-2",
        status="warn",
        duration_ms=20,
    )

    traces = list_traces()

    assert [t["trace_id"] for t in traces] == [second["trace_id"], first["trace_id"]]
    assert traces[0]["message"] == "第二条"
    assert traces[0]["session_id"] == "s-2"
    assert traces[1]["status"] == "ok"


def test_list_traces_respects_limit_and_clear_empties_store():
    record_trace(kind="chat", message="a", duration_ms=1)
    record_trace(kind="chat", message="b", duration_ms=2)

    assert len(list_traces(limit=1)) == 1
    assert list_traces(limit=1)[0]["message"] == "b"

    clear_traces()
    assert list_traces() == []
