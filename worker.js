// NXTL webhook receiver for Cloudflare Workers (single file).
// Built against the published NXTL API reference; not yet tested against the live API.
// Maintained by NXTL eSIM - https://nxtlsim.com
// Secrets: NXTL_WEBHOOK_SECRET, SLACK_WEBHOOK_URL (wrangler secret put ...)

const TOLERANCE = 300;

async function verify(raw, header, secret) {
  if (!header || !secret) return false;
  const parts = Object.fromEntries(header.split(",").map((p) => p.trim().split("=", 2)));
  const t = parts.t, v1 = parts.v1;
  if (!t || !v1 || v1.length !== 64 || !/^\d+$/.test(t)) return false;
  if (Math.abs(Date.now() / 1000 - Number(t)) > TOLERANCE) return false;
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(`${t}.${raw}`)));
  const hex = [...sig].map((b) => b.toString(16).padStart(2, "0")).join("");
  let diff = 0;
  for (let i = 0; i < 64; i++) diff |= hex.charCodeAt(i) ^ v1.charCodeAt(i);
  return diff === 0;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method !== "POST" || url.pathname !== "/webhooks/nxtl") return new Response("Not found", { status: 404 });
    const raw = await request.text();
    if (!(await verify(raw, request.headers.get("X-NXTL-Signature-V1"), env.NXTL_WEBHOOK_SECRET))) {
      return new Response("invalid signature", { status: 401 });
    }
    const evt = JSON.parse(raw);
    if (env.SLACK_WEBHOOK_URL) {
      await fetch(env.SLACK_WEBHOOK_URL, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text: `NXTL event *${evt.event}* (${evt.id})` }),
      });
    }
    return Response.json({ ok: true });
  },
};
