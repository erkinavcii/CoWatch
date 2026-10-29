import pytest

from server import room as room_module
from server.room import Room


@pytest.fixture
def clock(monkeypatch):
    state = {"ms": 1_000_000.0}
    monkeypatch.setattr(room_module, "now_ms", lambda: state["ms"])

    def advance(seconds: float) -> None:
        state["ms"] += seconds * 1000

    return advance


def test_position_runs_only_while_playing(clock):
    room = Room()
    clock(5)
    assert room.current_position() == 0
    assert room.play() is True
    assert room.play() is False  # already playing: nothing to broadcast
    clock(10)
    assert room.current_position() == pytest.approx(10)
    room.pause()
    clock(30)
    assert room.current_position() == pytest.approx(10)


def test_buffering_client_holds_the_room(clock):
    room = Room()
    viewer = room.add(None)
    room.play()
    clock(4)
    assert room.set_buffering(viewer, True) is True
    clock(6)
    assert room.current_position() == pytest.approx(4)  # frozen while someone buffers
    assert room.state_msg()["waiting"] == [viewer.id]
    room.set_buffering(viewer, False)
    clock(2)
    assert room.current_position() == pytest.approx(6)


def test_leaving_while_buffering_releases_the_room(clock):
    room = Room()
    viewer = room.add(None)
    room.play()
    room.set_buffering(viewer, True)
    clock(3)
    assert room.remove(viewer.id) is True
    clock(2)
    assert room.current_position() == pytest.approx(2)


def test_seek_and_loading(clock):
    room = Room()
    room.play()
    clock(2)
    room.seek(100)
    room.set_loading(True)
    clock(5)
    assert room.current_position() == pytest.approx(100)
    room.set_loading(False)
    clock(1)
    assert room.current_position() == pytest.approx(101)
    assert room.seq > 0


def test_screen_share_requests_run_out():
    import time
    from server.room import SHARE_ASK_TIMEOUT_S
    room = Room()
    room.share_asks = {"old": time.monotonic() - SHARE_ASK_TIMEOUT_S - 1, "new": time.monotonic()}
    assert room.expired_share_asks() == ["old"]
    assert room.screen_msg() == {"type": "screen", "owner": None, "pending": ["old", "new"]}
