import hashlib, hmac, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["NXTL_WEBHOOK_SECRET"] = "whsec_test"
from fastapi.testclient import TestClient
from app import app, verify_nxtl_signature

SECRET = "whsec_test"
BODY = json.dumps({"id": "evt_1", "event": "test.ping", "timestamp": 1, "data": {}}).encode()


def sign(body, ts, secret=SECRET):
    return f"t={ts},v1=" + hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()


def test_valid():
    ts = int(time.time())
    assert verify_nxtl_signature(BODY, sign(BODY, ts), SECRET)


def test_wrong_secret():
    assert not verify_nxtl_signature(BODY, sign(BODY, int(time.time()), "other"), SECRET)


def test_tampered_body():
    ts = int(time.time())
    assert not verify_nxtl_signature(BODY + b" ", sign(BODY, ts), SECRET)


def test_stale_timestamp():
    ts = int(time.time()) - 3600
    assert not verify_nxtl_signature(BODY, sign(BODY, ts), SECRET)
    assert verify_nxtl_signature(BODY, sign(BODY, ts), SECRET, tolerance=0)


def test_malformed_headers():
    for h in ["", "garbage", "t=1", "v1=abc", "t=abc,v1=" + "0" * 64, "t=1,v1=short"]:
        assert not verify_nxtl_signature(BODY, h, SECRET)


def test_endpoint():
    c = TestClient(app)
    ts = int(time.time())
    assert c.post("/webhooks/nxtl", content=BODY, headers={"X-NXTL-Signature-V1": sign(BODY, ts)}).status_code == 200
    assert c.post("/webhooks/nxtl", content=BODY, headers={"X-NXTL-Signature-V1": "t=1,v1=" + "0" * 64}).status_code == 401
