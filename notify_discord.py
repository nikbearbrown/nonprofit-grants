#!/usr/bin/env python3
"""Post NEW Humanitarians AI leads to a Discord channel.

    NOTIFY_WEBHOOK_FILE=/path/to/webhook NOTIFY_STATE=/path/to/posted.json python3 notify_discord.py [--dry-run] [--test]

Reads data/hai-relevant.json. An id is added to the state file only after Discord accepted the message that
contained it, so a failed run repeats instead of silently losing leads. The webhook URL is read from a file
and never printed or committed.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
UA = "nonprofit-grants-notifier/0.1 (+https://github.com/nikbearbrown/nonprofit-grants)"
LIMIT = 1800  # Discord's cap is 2000 characters per message


def line(r):
    when = r["deadline"] or "rolling or no date stated"
    who = " · ".join(x for x in (r.get("funder"), r.get("amount_text")) if x)
    check = "" if r.get("verified") else " (not checked on the funder's page)"
    return f"• **{r['name']}** — {when}{(' — ' + who) if who else ''}{check}\n  <{r['url']}>"


def chunks(rows, header):
    out, cur = [], header
    for r in rows:
        piece = ([r], line(r))
        if len(cur) + len(piece[1]) + 1 > LIMIT and cur != header:
            out.append((cur, [x["id"] for x in batch]))
            cur = header
            batch = []
        if cur == header:
            batch = []
        cur += "\n" + piece[1]
        batch.append(r)
    if cur != header:
        out.append((cur, [x["id"] for x in batch]))
    return out


def post(url, text):
    body = json.dumps({"content": text, "allowed_mentions": {"parse": []}}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": UA})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 0:
                time.sleep(min(float(e.headers.get("Retry-After", "2")), 10))
                continue
            return e.code
    return 0


def main(argv):
    dry, test = "--dry-run" in argv, "--test" in argv
    hook_file = os.environ.get("NOTIFY_WEBHOOK_FILE", "")
    state_path = os.environ.get("NOTIFY_STATE", os.path.join(ROOT, "posted.json"))
    url = open(hook_file).read().strip() if hook_file and os.path.exists(hook_file) else ""
    if not dry and not url:
        print("no webhook file; nothing posted")
        return 1
    if test:
        status = post(url, "Grant leads for Humanitarians AI: test message. Daily posts will list only new leads.")
        print("test message HTTP", status)
        return 0 if status in (200, 204) else 1

    rows = json.load(open(os.path.join(ROOT, "data", "hai-relevant.json"), encoding="utf-8"))
    seen = set(json.load(open(state_path))) if os.path.exists(state_path) else set()
    new = [r for r in rows if r["id"] not in seen]
    print(f"{len(rows)} Humanitarians AI leads, {len(new)} new")
    if not new:
        return 0
    header = f"**{len(new)} grant lead{'s' if len(new) != 1 else ''} for Humanitarians AI.** Leads, not plans: check the funder's page before anyone applies. Full list: <https://github.com/nikbearbrown/hai-grants/tree/main/watchlist>"
    for text, ids in chunks(new, header):
        if dry:
            print(text, "\n---")
            continue
        status = post(url, text)
        if status not in (200, 204):
            print("Discord refused a message, HTTP", status, "; stopping, nothing from this message marked as posted")
            return 1
        seen.update(ids)
        os.makedirs(os.path.dirname(os.path.abspath(state_path)), exist_ok=True)
        json.dump(sorted(seen), open(state_path, "w"))
        time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
