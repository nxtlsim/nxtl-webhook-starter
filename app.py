"""nxtl-webhook-starter: verify NXTL webhook signatures and forward events to Slack.

Built against the published NXTL API reference (https://nxtlsim.com/nxtl-api-reference/);
not yet tested against the live API. Maintained by NXTL eSIM (https://nxtlsim.com).

Header: X-NXTL-Signature-V1: t=<unix_timestamp>,v1=<hmac_sha256_hex>
Signed payload: "{t}.{raw_body}" with your webhook secret (HMAC-SHA256).
"""
import hashlib, hmac, json, os, time
import requests
from fastapi import FastAPI, HTTPException, Request

SIGNATURE_HEADER = "X-NXTL-Signature-V1"
TOLERANCE_SECONDS = int(os.environ.get("NXTL_WEBHOOK_TOLERANCE", "300"))


def verify_nxtl_signature(raw_body: bytes, header: str, secret: str,
                          tolerance: int = TOLERANCE_SECONDS, now: float | None = None) -> bool:
    if not header or not secret:
        return False
    try:
        parts = dict(p.strip().split("=", 1) for p in header.split(","))
    except ValueError:
        return False
    ts, v1 = parts.get("t"), parts.get("v1")
    if not ts or not v1 or len(v1) != 64 or not ts.isdigit():
        return False
    if tolerance and abs((now or time.time()) - int(ts)) > tolerance:
        return False  # replay protection (our addition; tune via NXTL_WEBHOOK_TOLERANCE, 0 disables)
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, v1)


def format_event(evt: dict) -> str:
    data = evt.get("data") or {}
    summary = ", ".join(f"{k}={v}" for k, v in list(data.items())[:6])
    return f"NXTL event *{evt.get('event', 'unknown')}* ({evt.get('id', '-')}) {summary}"


app = FastAPI(title="NXTL webhook starter")
_seen: set[str] = set()


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/webhooks/nxtl")
async def nxtl_webhook(request: Request):
    raw = await request.body()  # verify the RAW body before parsing JSON
    if not verify_nxtl_signature(raw, request.headers.get(SIGNATURE_HEADER, ""),
                                 os.environ.get("NXTL_WEBHOOK_SECRET", "")):
        raise HTTPException(status_code=401, detail="invalid signature")
    evt = json.loads(raw)
    if evt.get("id") in _seen:  # deliveries can be retried or replayed
        return {"ok": True, "duplicate": True}
    _seen.add(evt.get("id"))
    slack = os.environ.get("SLACK_WEBHOOK_URL")
    if slack:
        requests.post(slack, json={"text": format_event(evt)}, timeout=10)
    return {"ok": True}
