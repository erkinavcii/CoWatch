from fastapi.testclient import TestClient

from server.main import app
from server.signaling import MAX_RTC_BYTES, ice_servers, rtc_data
from tests.test_presence import _members_until, _next

KEY = "test-key"


def test_rtc_data_keeps_descriptions_and_candidates_only():
    offer = {"description": {"type": "offer", "sdp": "v=0\r\n", "extra": 1}}
    assert rtc_data(offer) == {"description": {"type": "offer", "sdp": "v=0\r\n"}}
    candidate = {"candidate": {"candidate": "candidate:1 1 udp 1 100.64.0.7 5000 typ host", "sdpMid": "0"}}
    assert rtc_data(candidate) == candidate
    assert rtc_data({"candidate": None}) == {"candidate": None}  # end of candidates
    assert rtc_data({"reset": True}) == {"reset": True}
    assert rtc_data({"reset": "yes"}) is None
    assert rtc_data({"description": {"type": "hack", "sdp": ""}}) is None
    assert rtc_data({"description": {"type": "offer", "sdp": 5}}) is None
    assert rtc_data({"candidate": "x"}) is None
    assert rtc_data({"description": offer["description"], "candidate": None}) is None
    assert rtc_data("offer") is None
    assert rtc_data({"description": {"type": "offer", "sdp": "a" * MAX_RTC_BYTES}}) is None


def test_ice_servers_from_env_text():
    assert ice_servers("") == []
    assert ice_servers("stun:stun.example.org:3478, turn:relay.example.org , http://x, ") == [
        {"urls": "stun:stun.example.org:3478"}, {"urls": "turn:relay.example.org"}]


def test_rtc_goes_to_its_target_only_in_order_and_av_state_is_shared():
    with TestClient(app, cookies={"cw_key": KEY}) as client:
        with client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b, \
                client.websocket_connect("/ws") as c:
            a_id = _next(a, {"welcome"})["clientId"]
            b_id = _next(b, {"welcome"})["clientId"]
            assert _next(c, {"welcome"})["iceServers"] == []

            # Joined and microphone state reach everyone through the member list.
            a.send_json({"type": "hello", "name": "A", "mic": True})
            _members_until(b, lambda ms: any(m["id"] == a_id and m["joined"] and m["mic"] and not m["cam"]
                                             for m in ms))
            b.send_json({"type": "av", "mic": False, "cam": True})
            _members_until(a, lambda ms: any(m["id"] == b_id and m["cam"] and not m["joined"] for m in ms))

            # Signalling: only B gets it, with A's id written by the server, in order.
            for i in range(20):
                a.send_json({"type": "rtc", "to": b_id, "data": {"candidate": {"candidate": f"c{i}"}}})
            a.send_json({"type": "rtc", "to": a_id, "data": {"candidate": None}})  # to itself: dropped
            a.send_json({"type": "rtc", "to": "nobody", "data": {"candidate": None}})
            a.send_json({"type": "rtc", "to": b_id, "data": {"bogus": 1}})
            a.send_json({"type": "rtc", "to": b_id, "data": {"description": {"type": "offer", "sdp": "v=0"}}})
            got = [_next(b, {"rtc"}) for _ in range(21)]
            assert all(m["from"] == a_id for m in got)
            assert [m["data"]["candidate"]["candidate"] for m in got[:20]] == [f"c{i}" for i in range(20)]
            assert got[20]["data"] == {"description": {"type": "offer", "sdp": "v=0"}}

            # C saw none of it: its next rtc-or-pong is the pong.
            c.send_json({"type": "ping", "t0": 1})
            assert _next(c, {"rtc", "pong"})["type"] == "pong"
            a.send_json({"type": "ping", "t0": 2})
            assert _next(a, {"rtc", "pong"})["type"] == "pong"
