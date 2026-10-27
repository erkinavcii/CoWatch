from fastapi.testclient import TestClient

from server.main import app
from server.presence import MAX_POINTS, PALETTE, pick_color, point, stroke_message

KEY = "test-key"


def test_points_are_clamped_and_checked():
    assert point(0.25, "0.5") == (0.25, 0.5)
    assert point(9, -9) == (1.5, -0.5)
    assert point("nan", 0.5) is None
    assert point(None, 0.5) is None
    assert point(float("inf"), 0.5) is None


def test_pick_color_prefers_the_request_when_free():
    assert pick_color(None, set()) == PALETTE[0]
    assert pick_color(PALETTE[3].upper(), set()) == PALETTE[3]
    assert pick_color(PALETTE[0], {PALETTE[0]}) == PALETTE[1]
    assert pick_color("#123456", set()) == PALETTE[0]  # not in the palette
    assert pick_color(None, set(PALETTE)) in PALETTE  # everyone has a colour: share one


def test_stroke_message_keeps_only_valid_parts():
    out = stroke_message(
        {"id": "s1", "start": True, "color": "#ABCDEF", "points": [[0.1, 0.1], ["x", 1], [0.2], [0.2, 0.2]]},
        "abc", PALETTE[0],
    )
    assert out == {"type": "draw", "from": "abc", "stroke": "s1", "points": [[0.1, 0.1], [0.2, 0.2]],
                   "start": True, "color": "#abcdef"}
    assert stroke_message({"id": "s1", "start": True, "color": "red"}, "abc", PALETTE[2])["color"] == PALETTE[2]
    many = stroke_message({"id": "s1", "end": True, "points": [[0.5, 0.5]] * 300}, "abc", PALETTE[0])
    assert len(many["points"]) == MAX_POINTS and many["end"] is True
    assert stroke_message({"id": "../x", "points": [[0.1, 0.1]]}, "abc", PALETTE[0]) is None
    assert stroke_message({"id": "s1", "points": []}, "abc", PALETTE[0]) is None


def _next(ws, kinds):
    """The next message of one of `kinds`, skipping the rest (members, pongs...)."""
    for _ in range(50):
        msg = ws.receive_json()
        if msg["type"] in kinds:
            return msg
    raise AssertionError(f"no {kinds} message")


def _members_until(ws, check):
    for _ in range(50):
        msg = _next(ws, {"members"})
        if check(msg["members"]):
            return msg["members"]
    raise AssertionError("members never matched")


def test_colors_cursors_pokes_and_drawings_reach_the_others():
    with TestClient(app, cookies={"cw_key": KEY}) as client:
        with client.websocket_connect("/ws") as a:
            a_id = _next(a, {"welcome"})["clientId"]
            a.send_json({"type": "hello", "name": "A"})
            _members_until(a, lambda ms: any(m["id"] == a_id and m["color"] == PALETTE[0] for m in ms))

            with client.websocket_connect("/ws") as b:
                welcome = _next(b, {"welcome"})
                b_id = welcome["clientId"]
                assert welcome["palette"] == list(PALETTE)
                b.send_json({"type": "hello", "name": "B", "color": PALETTE[0]})  # taken by A
                _members_until(b, lambda ms: any(m["id"] == b_id and m["color"] == PALETTE[1] for m in ms))

                # Cursor positions go to the others only. If A got its own back, it would
                # arrive before B's (B only moves after seeing A's).
                a.send_json({"type": "cursor", "x": 0.25, "y": 0.5})
                assert _next(b, {"cursor"}) == {"type": "cursor", "from": a_id, "x": 0.25, "y": 0.5}
                b.send_json({"type": "cursor", "x": 7, "y": 0.1})
                assert _next(a, {"cursor"}) == {"type": "cursor", "from": b_id, "x": 1.5, "y": 0.1}

                # Bad positions are dropped; a second poke right after the first is too.
                a.send_json({"type": "cursor", "x": "nan", "y": 0.5})
                a.send_json({"type": "poke", "x": 0.5, "y": 0.5})
                a.send_json({"type": "poke", "x": 0.6, "y": 0.6})
                a.send_json({"type": "cursor", "hidden": True})
                assert _next(b, {"cursor", "poke"}) == {"type": "poke", "from": a_id, "x": 0.5, "y": 0.5}
                assert _next(b, {"cursor", "poke"}) == {"type": "cursor", "from": a_id, "hidden": True}

                # Strokes arrive in order, with the sender's id.
                a.send_json({"type": "draw", "id": "s1", "start": True, "color": PALETTE[0], "points": [[0.1, 0.2]]})
                a.send_json({"type": "draw", "id": "s1", "points": [[0.3, 0.4]], "end": True})
                first = _next(b, {"draw"})
                assert first["from"] == a_id and first["start"] and first["points"] == [[0.1, 0.2]]
                second = _next(b, {"draw"})
                assert second["points"] == [[0.3, 0.4]] and second["end"]

                b.send_json({"type": "draw_clear"})
                assert _next(a, {"draw_clear"}) == {"type": "draw_clear", "from": b_id}

                # Picking a colour from the toolbar; only palette colours are accepted.
                a.send_json({"type": "color", "color": "#123456"})
                a.send_json({"type": "color", "color": PALETTE[6].upper()})
                _members_until(b, lambda ms: any(m["id"] == a_id and m["color"] == PALETTE[6] for m in ms))
