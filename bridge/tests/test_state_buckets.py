import echo_filter
import push_state


def test_echo_filter_isolates_buckets(fake_clock):
    echo_filter.mark_injected("wrapper-rc", "hello")
    assert echo_filter.claim_echo("wrapper-rc", "hello") is True
    assert echo_filter.claim_echo("wrapper-xyz", "hello") is False


def test_echo_filter_claim_consumes(fake_clock):
    echo_filter.mark_injected("w1", "msg")
    assert echo_filter.claim_echo("w1", "msg") is True
    assert echo_filter.claim_echo("w1", "msg") is False


def test_push_state_per_wrapper():
    push_state.set_paused("w1", True)
    assert push_state.is_tool_use_paused("w1") is True
    assert push_state.is_tool_use_paused("w2") is False
    push_state.set_paused("w1", False)
    assert push_state.is_tool_use_paused("w1") is False


import files_tracker
import menu


def test_files_tracker_records_per_wrapper():
    files_tracker.clear("w1")
    files_tracker.clear("w2")
    files_tracker.record("w1", "Write", "/a.txt")
    files_tracker.record("w2", "Edit", "/b.txt")
    assert [p for _, _, p in files_tracker.list_recent("w1")] == ["/a.txt"]
    assert [p for _, _, p in files_tracker.list_recent("w2")] == ["/b.txt"]


def test_files_tracker_selection_per_wrapper():
    files_tracker.clear("w1")
    files_tracker.clear("w2")
    files_tracker.offer_selection("w1", ["/x.txt", "/y.txt"])
    files_tracker.offer_selection("w2", ["/z.txt"])
    assert files_tracker.try_select("w1", "1") == "/x.txt"
    assert files_tracker.try_select("w2", "1") == "/z.txt"
    # consumed
    assert files_tracker.try_select("w1", "1") is None


def test_menu_selection_per_wrapper():
    menu.offer_menu("w1")
    menu.offer_menu("w2")
    cmd1 = menu.try_consume_choice("w1", "1")
    cmd2 = menu.try_consume_choice("w2", "2")
    assert cmd1 == menu.COMMANDS[0]
    assert cmd2 == menu.COMMANDS[1]
    # each bucket consumed independently
    assert menu.try_consume_choice("w1", "1") is None
    assert menu.try_consume_choice("w2", "1") is None


import history
import image_cache


def test_history_per_wrapper():
    history.remember("w1", "C:\\proj1\\transcript.jsonl")
    history.remember("w2", "C:\\proj2\\transcript.jsonl")
    assert history.current_transcript("w1") == "C:\\proj1\\transcript.jsonl"
    assert history.current_transcript("w2") == "C:\\proj2\\transcript.jsonl"
    assert history.current_transcript("w3") == ""


def test_image_cache_per_wrapper_subdir(tmp_path, monkeypatch):
    monkeypatch.setattr(image_cache, "_BASE_DIR", tmp_path)
    p1 = image_cache.save_image_bytes("w1", b"abc", "x.png")
    p2 = image_cache.save_image_bytes("w2", b"def", "y.png")
    assert "\\w1\\" in p1 or "/w1/" in p1
    assert "\\w2\\" in p2 or "/w2/" in p2
