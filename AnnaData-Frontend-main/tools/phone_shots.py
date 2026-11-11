"""Drive headless Chrome over CDP through a list of steps, saving phone screenshots.

usage: python cdp_shots.py <steps.json> <out_dir>

steps.json: a list of runs; each run is {"name": ..., "steps": [...]} and starts
on a fresh tab at http://localhost:3000 (the browser profile persists across
runs, like a real phone). Step forms:
  ["wait", seconds]
  ["click", text]            first visible button/link/[role] whose aria-label,
                             title or text contains `text` (case-insensitive)
  ["clicksel", css]
  ["type", css, text]        sets the value React-style and fires input
  ["key", "Enter"]
  ["upload", css, path]
  ["eval", js]
  ["scroll", css_or_null, y] scrolls a container (or the window) to y; -1 = bottom
  ["shot", name]
  ["waitfor", text, seconds] waits until the page text contains `text`
"""
import asyncio
import base64
import json
import os
import subprocess
import sys
import time

import requests
import websockets

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9333
APP = "http://localhost:3000"


class Tab:
    def __init__(self, ws):
        self.ws, self.n, self.pending = ws, 0, {}

    async def call(self, method, **params):
        self.n += 1
        msg_id = self.n
        await self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params}))
        while True:
            msg = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=30))
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    async def js(self, expr):
        r = await self.call("Runtime.evaluate", expression=expr, awaitPromise=True,
                            returnByValue=True)
        if r.get("exceptionDetails"):
            raise RuntimeError(f"js error: {r['exceptionDetails'].get('text')} :: {expr[:120]}")
        return r.get("result", {}).get("value")


FIND = r"""
(t => {
  t = t.toLowerCase();
  const els = [...document.querySelectorAll('button, a, [role=button], [role=menuitem], [role=tab], label, summary')];
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const hit = els.find(e => vis(e) && ((e.getAttribute('aria-label')||'') + ' ' + (e.title||'') + ' ' + (e.innerText||'')).toLowerCase().includes(t));
  if (!hit) return false;
  hit.scrollIntoView({block: 'center'}); hit.click(); return true;
})(%s)
"""

TYPE = r"""
((sel, text) => {
  const el = document.querySelector(sel); if (!el) return false;
  const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, text);
  el.dispatchEvent(new Event('input', {bubbles: true}));
  el.focus(); return true;
})(%s, %s)
"""


async def run(tab, steps, out_dir, log):
    for step in steps:
        kind, args = step[0], step[1:]
        if kind == "wait":
            await asyncio.sleep(args[0])
        elif kind == "click":
            ok = await tab.js(FIND % json.dumps(args[0]))
            log(f"  click {args[0]!r}: {ok}")
            await asyncio.sleep(1.2)
        elif kind == "clicksel":
            ok = await tab.js(f"(e=>{{if(!e)return false;e.click();return true}})(document.querySelector({json.dumps(args[0])}))")
            log(f"  clicksel {args[0]!r}: {ok}")
            await asyncio.sleep(1.2)
        elif kind == "type":
            ok = await tab.js(TYPE % (json.dumps(args[0]), json.dumps(args[1])))
            log(f"  type {args[0]!r}: {ok}")
            await asyncio.sleep(0.4)
        elif kind == "key":
            for t in ("keyDown", "keyUp"):
                await tab.call("Input.dispatchKeyEvent", type=t, key=args[0], code=args[0],
                               windowsVirtualKeyCode=13 if args[0] == "Enter" else 0)
            await asyncio.sleep(0.5)
        elif kind == "upload":
            doc = await tab.call("DOM.getDocument")
            node = await tab.call("DOM.querySelector", nodeId=doc["root"]["nodeId"], selector=args[0])
            await tab.call("DOM.setFileInputFiles", files=[args[1]], nodeId=node["nodeId"])
            log(f"  upload {os.path.basename(args[1])}")
            await asyncio.sleep(1.5)
        elif kind == "eval":
            log(f"  eval -> {await tab.js(args[0])!r}"[:300])
        elif kind == "scroll":
            sel, y = args
            target = f"document.querySelector({json.dumps(sel)})" if sel else "document.scrollingElement"
            await tab.js(f"(e=>{{if(!e)return; e.scrollTop = {y} < 0 ? e.scrollHeight : {y};}})({target})")
            await asyncio.sleep(0.8)
        elif kind == "waitfor":
            text, secs = args
            end = time.time() + secs
            found = False
            while time.time() < end:
                if await tab.js(f"document.body.innerText.toLowerCase().includes({json.dumps(text.lower())})"):
                    found = True
                    break
                await asyncio.sleep(0.5)
            log(f"  waitfor {text!r}: {found}")
        elif kind == "shot":
            await tab.call("Page.bringToFront")
            shot = await tab.call("Page.captureScreenshot", format="png", fromSurface=True)
            path = os.path.join(out_dir, f"{args[0]}.png")
            with open(path, "wb") as f:
                f.write(base64.b64decode(shot["data"]))
            log(f"  shot {path}")


async def main(steps_file, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    runs = json.load(open(steps_file, encoding="utf-8"))
    # The browser profile lives outside the repo and is thrown away by the
    # caller afterwards: it grows past 100 MB and the founder's disk is small.
    profile = os.environ.get("PHONE_SHOTS_PROFILE") or os.path.join(
        os.environ.get("TEMP", "/tmp"), "annadata-phone-shots-profile")
    proc = subprocess.Popen([
        CHROME, "--headless=new", f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}",
        "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
        "--no-first-run", "--window-size=375,812", "--no-default-browser-check", "--hide-scrollbars", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                requests.get(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
                break
            except Exception:
                time.sleep(0.3)
        target = requests.put(f"http://127.0.0.1:{PORT}/json/new?about:blank", timeout=10).json()
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=50_000_000) as ws:
            tab = Tab(ws)
            await tab.call("Page.enable")
            await tab.call("Runtime.enable")
            await tab.call("Page.bringToFront")
            await tab.call("Emulation.setDeviceMetricsOverride", width=375, height=812,
                           deviceScaleFactor=2, mobile=True)
            await tab.call("Emulation.setTouchEmulationEnabled", enabled=True, maxTouchPoints=5)
            await tab.call("Emulation.setUserAgentOverride", userAgent=(
                "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"))
            for perm_call in (
                ("Browser.grantPermissions", {"permissions": ["geolocation", "audioCapture"], "origin": APP}),
                ("Emulation.setGeolocationOverride", {"latitude": 22.346, "longitude": 87.232, "accuracy": 50}),
            ):
                try:
                    await tab.call(perm_call[0], **perm_call[1])
                except Exception as e:
                    print(f"  ({perm_call[0]} unavailable: {e})", flush=True)
            for r in runs:
                print(f"== {r['name']}", flush=True)
                w, h, mob = r.get("viewport", [375, 812, True])
                await tab.call("Emulation.setDeviceMetricsOverride", width=w, height=h,
                               deviceScaleFactor=2 if mob else 1.5, mobile=mob)
                await tab.call("Page.navigate", url=r.get("url", APP))
                await asyncio.sleep(r.get("load_wait", 4))
                try:
                    await run(tab, r["steps"], out_dir, lambda m: print(m, flush=True))
                except Exception as e:
                    print(f"  FAILED: {e}", flush=True)
    finally:
        proc.terminate()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
