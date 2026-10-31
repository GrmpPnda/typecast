"""Screenshot a page as a phone sees it, for checking the mobile layout.

    backend/.venv/bin/python scripts/dev/phone-screenshot.py [--desktop] [--check] OUT.png URL [JS ...]

Drives Chrome over the DevTools protocol with a true 390x844 mobile viewport,
touch, and an iPhone user agent. Each JS argument runs after the page loads
(for example, to click a button), with a pause after each; its value, or the
error it raised, is printed. --desktop uses a 1280x800 desktop window instead,
which also works for the chapter view, where plain headless screenshots hang.
--check reports form controls that stick out of any box they sit in, which is
how a too-wide grid column or an unshrinkable select shows up on a phone. The
page itself can fit the screen while a dropdown overhangs its card, so the page
width alone does not catch it.

A plain `--window-size=390,844` is not a phone: desktop Chrome keeps a minimum
window width of about 500px, so such screenshots look clipped on the right.
Needs Google Chrome and the `websockets` package (installed with uvicorn).
"""

import asyncio
import base64
import json
import subprocess
import sys
import tempfile
import time
import urllib.request

import websockets

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9333
# Controls whose right edge passes an enclosing box, up to the first box that
# clips or scrolls. Stops at positioned layers, which escape their ancestors.
OVERHANG_CHECK = """(() => {
  const bad = [];
  for (const el of document.querySelectorAll('select, input, textarea, button')) {
    const r = el.getBoundingClientRect();
    if (!r.width || ['absolute', 'fixed'].includes(getComputedStyle(el).position)) continue;
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      const cs = getComputedStyle(p);
      if (r.right > p.getBoundingClientRect().right + 1) {
        const label = el.title || el.getAttribute('aria-label') || el.textContent.trim() || el.tagName;
        bad.push(label.slice(0, 24) + ' +' + Math.round(r.right - p.getBoundingClientRect().right) + 'px');
        break;
      }
      if (cs.overflowX !== 'visible' || ['absolute', 'fixed'].includes(cs.position)) break;
    }
  }
  return bad.length ? 'controls overhang their box: ' + bad.join(', ') : 'no controls overhang';
})()"""

IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
)


async def main(out: str, url: str, scripts: list[str], desktop: bool = False,
               check: bool = False) -> None:
    profile = tempfile.mkdtemp()
    chrome = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", f"--remote-debugging-port={PORT}",
         f"--user-data-dir={profile}", "--ignore-certificate-errors", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        page = None
        for _ in range(50):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
                page = next(t for t in targets if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.2)
        if page is None:
            sys.exit("Chrome did not start")
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=None) as ws:
            next_id = 0

            async def call(method: str, **params):
                nonlocal next_id
                next_id += 1
                await ws.send(json.dumps({"id": next_id, "method": method, "params": params}))
                while True:
                    message = json.loads(await ws.recv())
                    if message.get("id") == next_id:
                        return message.get("result", {})

            if desktop:
                await call("Emulation.setDeviceMetricsOverride",
                           width=1280, height=800, deviceScaleFactor=1, mobile=False)
            else:
                await call("Emulation.setDeviceMetricsOverride",
                           width=390, height=844, deviceScaleFactor=2, mobile=True)
                await call("Emulation.setTouchEmulationEnabled", enabled=True, maxTouchPoints=5)
                await call("Emulation.setUserAgentOverride", userAgent=IPHONE)
            await call("Page.enable")
            await call("Page.navigate", url=url)
            await asyncio.sleep(5)
            for script in scripts + ([OVERHANG_CHECK] if check else []):
                result = await call("Runtime.evaluate", expression=script,
                                    awaitPromise=True, returnByValue=True)
                if "exceptionDetails" in result:
                    detail = result["exceptionDetails"]
                    print("js error:", detail.get("exception", {}).get("description") or detail.get("text"))
                value = result.get("result", {}).get("value")
                if value is not None:
                    print("js:", value)
                await asyncio.sleep(1.5)
            shot = await call("Page.captureScreenshot", format="png")
            with open(out, "wb") as f:
                f.write(base64.b64decode(shot["data"]))
            widths = await call("Runtime.evaluate", returnByValue=True,
                                expression="[document.documentElement.scrollWidth, innerWidth]")
            scroll, inner = widths["result"]["value"]
            print(f"{out}: page width {scroll}px in a {inner}px viewport"
                  + ("" if scroll <= inner else "  <-- overflows sideways"))
    finally:
        chrome.terminate()


if __name__ == "__main__":
    args = sys.argv[1:]
    desktop, check = "--desktop" in args, "--check" in args
    args = [a for a in args if a not in ("--desktop", "--check")]
    if len(args) < 2:
        sys.exit(__doc__)
    asyncio.run(main(args[0], args[1], args[2:], desktop, check))
