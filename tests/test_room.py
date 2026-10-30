import asyncio

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


class SlowSocket:
    """Takes a moment per message, like a slow link; records what arrived."""

    def __init__(self):
        self.got = []

    async def send_json(self, msg):
        await asyncio.sleep(0.01)
        self.got.append(msg)


def test_a_held_back_pointer_position_still_arrives_and_only_the_newest():
    from server.room import Client

    async def scenario():
        ws = SlowSocket()
        client = Client(ws)
        first = asyncio.create_task(client.send({"type": "cursor", "from": "a", "x": 0.1}, lossy=True))
        await asyncio.sleep(0)  # the first is on its way
        for x in (0.2, 0.3, 0.4):
            assert await client.send({"type": "cursor", "from": "a", "x": x}, lossy=True)
        await client.send({"type": "cursor", "from": "b", "x": 0.9}, lossy=True)
        await first
        return ws.got

    got = asyncio.run(scenario())
    # The last position of each sender arrives; the ones in between give way.
    assert [(m["from"], m["x"]) for m in got] == [("a", 0.1), ("a", 0.4), ("b", 0.9)]


def test_a_hidden_pointer_is_not_overtaken_by_an_older_position():
    from server.room import Client

    async def scenario():
        ws = SlowSocket()
        client = Client(ws)
        first = asyncio.create_task(client.send({"type": "chat", "from": "x"}))
        await asyncio.sleep(0)
        await client.send({"type": "cursor", "from": "a", "x": 0.5}, lossy=True)  # held back
        await client.send({"type": "cursor", "from": "a", "hidden": True})
        await first
        return ws.got

    got = asyncio.run(scenario())
    assert got[-1] == {"type": "cursor", "from": "a", "hidden": True}
    assert not any(m.get("x") == 0.5 for m in got)
