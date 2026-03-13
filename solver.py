import os
import time
import json
import requests
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────────────────
BASE_URL     = "https://apiweb.wintercode.dev"
API_KEY      = os.environ["WH_API_KEY"]
COOKIES_RAW  = os.environ["WH_COOKIES"]       # newline-separated cookies
PLACE_ID     = int(os.environ.get("PLACE_ID", "4483381587"))
DELAY_COOKIE = float(os.environ.get("DELAY_COOKIE", "5"))   # seconds between cookies
DELAY_LOOP   = float(os.environ.get("DELAY_LOOP", "600"))    # seconds between loops
SOLVE_POW    = os.environ.get("SOLVE_POW", "true").lower() == "true"
SOLVE_POS    = os.environ.get("SOLVE_POS", "true").lower() == "true"
SOLVE_CAP    = os.environ.get("SOLVE_CAP", "true").lower() == "true"
# ────────────────────────────────────────────────────────────────────────────

HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

def log(msg, tag="INFO"):
    ts = datetime.utcnow().strftime("%H:%M:%S")
    print(f"[{ts}] [{tag}] {msg}")

def load_cookies():
    cookies = [c.strip() for c in COOKIES_RAW.splitlines() if c.strip()]
    log(f"Loaded {len(cookies)} cookies")
    return cookies

def solve(endpoint, cookie, label):
    try:
        res = requests.post(
            f"{BASE_URL}{endpoint}",
            headers=HEADERS,
            json={"cookie": cookie, "placeId": PLACE_ID},
            timeout=60
        )
        data = res.json()
        status = data.get("status", "UNKNOWN")
        success = data.get("success", False)

        if success:
            if "NO_CHALLENGE" in status or "NO_CAPTCHA" in status:
                log(f"{label} → {status} (refunded)", "SKIP")
            else:
                solve_time = data.get("solve_time", "?")
                log(f"{label} → {status} in {solve_time}s ✓", "OK")
        else:
            log(f"{label} → FAILED: {status}", "FAIL")

        return status

    except requests.exceptions.Timeout:
        log(f"{label} → Timeout", "ERR")
        return "TIMEOUT"
    except Exception as e:
        log(f"{label} → Error: {e}", "ERR")
        return "ERROR"

def solve_cookie(cookie, index, total):
    short = cookie[:30] + "..."
    log(f"Cookie {index+1}/{total}: {short}")

    if SOLVE_POW:
        status = solve("/api/pow/solve", cookie, "PoW")
        time.sleep(1)

        # If captcha appeared during PoW, solve it first
        if "CAPTCHA" in status and SOLVE_CAP:
            log("Captcha detected after PoW — solving...", "CAP")
            solve("/api/captcha/solve", cookie, "Captcha")
            time.sleep(2)
            # Retry PoW after captcha
            solve("/api/pow/solve", cookie, "PoW retry")
            time.sleep(1)

    if SOLVE_POS:
        status = solve("/api/pow/solve", cookie, "PoS")
        time.sleep(1)

        if "CAPTCHA" in status and SOLVE_CAP:
            log("Captcha detected after PoS — solving...", "CAP")
            solve("/api/captcha/solve", cookie, "Captcha")
            time.sleep(2)
            solve("/api/pow/solve", cookie, "PoS retry")
            time.sleep(1)

def fetch_balance():
    try:
        res = requests.get(
            f"{BASE_URL}/api/captcha/balance",
            headers=HEADERS,
            timeout=15
        )
        data = res.json()
        if data.get("success") and data.get("data"):
            wh = data["data"].get("winterhub", {})
            yc = data["data"].get("yescaptcha", {})
            log(f"Balance — WH: Rp{wh.get('balance','?')} | Solves: {wh.get('totalSolves','?')} | YesCaptcha: {yc.get('balance','?')}", "BAL")
    except Exception as e:
        log(f"Balance check failed: {e}", "ERR")

def main():
    cookies = load_cookies()
    if not cookies:
        log("No cookies found — exiting", "ERR")
        return

    loop = 0
    # GitHub Actions jobs max out at 6 hours — run for ~5.5 hours then exit cleanly
    deadline = time.time() + (5.5 * 3600)

    while time.time() < deadline:
        loop += 1
        log(f"━━━ Loop #{loop} — {len(cookies)} cookies ━━━", "LOOP")
        fetch_balance()

        for i, cookie in enumerate(cookies):
            if time.time() >= deadline:
                log("Approaching time limit — stopping cleanly", "INFO")
                break
            solve_cookie(cookie, i, len(cookies))
            time.sleep(DELAY_COOKIE)

        log(f"Loop #{loop} done. Waiting {DELAY_LOOP}s before next loop...", "LOOP")
        fetch_balance()

        remaining = deadline - time.time()
        wait = min(DELAY_LOOP, remaining - 60)
        if wait > 0:
            time.sleep(wait)

    log("Job complete (time limit reached). GitHub Actions will restart it.", "INFO")

if __name__ == "__main__":
    main()
