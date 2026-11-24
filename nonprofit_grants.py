#!/usr/bin/env python3
"""Collect small-grant opportunities for nonprofits and write them out as data and readable markdown.

    python3 nonprofit_grants.py run      # fetch feeds, merge into data/, rewrite the markdown
    python3 nonprofit_grants.py render   # rewrite the markdown from data/ only (no network)

Standard library only. Inputs: sources.json (feeds), curated.json (hand-checked rows).
Outputs: data/opportunities.json (record), data/opportunities.csv, README.md, lists/*, topics/*,
data/hai-relevant.json (the subset a Humanitarians AI reader should look at first).
"""
import argparse
import csv
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
STORE = os.path.join(DATA, "opportunities.json")
DATE_FORMATS = ("%m/%d/%Y", "%d-%b-%y", "%d-%b-%Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%Y-%m-%d")
FFN_LABELS = ["Donor Name", "State", "County", "Type of Grant", "Deadline", "Size of the Grant", "Grant Duration", "Details"]
META_TAGS = {"All Proposals", "How to Apply", "Article Contributions", "Latest and Upcoming Grants for Nonprofit Organizations"}
LEAD_TITLE = re.compile(r"^(apply|call for|applications?|rfp|open call|submit|deadline|us (funders|grant))", re.I)  # article titles that announce a call
HAI_STATES = {"", "All States", "Massachusetts"}  # Humanitarians AI is a Boston-area US 501(c)(3)


def today():
    return dt.date.today()


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def make_id(url):
    return hashlib.sha1(url.strip().encode("utf-8")).hexdigest()[:16]


def strip_html(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def parse_date(text):
    text = (text or "").strip().rstrip(".")
    for fmt in DATE_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def ffn_field(summary, label):
    stops = "|".join(re.escape(s) + ":" for s in FFN_LABELS if s != label)
    m = re.search(re.escape(label) + r":\s*(.+?)(?=\s(?:" + stops + r")|$)", summary)
    return m.group(1).strip() if m else ""


def status_for(deadline_iso, declared=None):
    if deadline_iso:
        return "open" if dt.date.fromisoformat(deadline_iso) >= today() else "closed"
    return declared if declared in ("open", "closed", "unknown") else "unknown"


def is_relevant(rec, cfg, kind):
    """Keyword match for AI / humanitarian / nonprofit-tech work (used for the Humanitarians AI list)."""
    text = " " + " ".join([rec["name"], rec["summary"], " ".join(rec["tags"])]).lower() + " "
    if not any(k in text for k in cfg["relevance_any"]):
        return False
    return kind != "news" or any(w in text for w in cfg["grant_words"])


def fetch(url, ua, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_feed(xml_bytes, source_id, kind, cfg):
    out = []
    for it in ET.fromstring(xml_bytes).iter("item"):
        link = (it.findtext("link") or "").strip()
        if not link:
            continue
        summary = strip_html(it.findtext("description"))
        tags = [c.text.strip() for c in it.findall("category") if c.text]
        ffn = "Deadline:" in summary
        d = parse_date(ffn_field(summary, "Deadline")) if ffn else None
        deadline = d.isoformat() if d else None
        rec = {
            "id": make_id(link), "name": strip_html(it.findtext("title")),
            "funder": ffn_field(summary, "Donor Name") if ffn else "", "url": link, "source": source_id,
            "deadline": deadline, "amount_text": ffn_field(summary, "Size of the Grant") if ffn else "",
            "eligibility": "", "state": ffn_field(summary, "State") if ffn else "", "summary": summary[:400],
            "tags": tags[:12], "status": status_for(deadline), "verified": False, "url_verified": False,
        }
        rec["relevant"] = is_relevant(rec, cfg, kind)
        out.append(rec)
    return out


def curated_rows():
    rows = []
    for r in load_json(os.path.join(ROOT, "curated.json"), {"rows": []})["rows"]:
        rec = {"id": make_id(r["url"] + "|" + r["name"]), "source": "curated", "state": "", "summary": "", "tags": [],
               "relevant": True, "funder": "", "eligibility": "", "amount_text": "", **r}
        rec["status"] = status_for(rec["deadline"], r.get("status"))
        rows.append(rec)
    return rows


def merge(store, fresh):
    now = today().isoformat()
    for rec in fresh:
        rec["summary"] = ""  # keep other sites' descriptive text out of the public data; relevance was computed from it already
        old = store.get(rec["id"])
        rec["first_seen"] = old["first_seen"] if old else now
        rec["last_seen"] = now
        store[rec["id"]] = rec
    for rec in store.values():  # a deadline can pass between runs
        rec["summary"] = ""
        rec["status"] = status_for(rec["deadline"], None if rec["deadline"] else rec["status"])
    return store


# ---------- classification ----------

def section(r):
    """Where a row is listed. 'skip' rows (sample proposals, how-to articles) stay in the data but are not shown."""
    u = r["url"]
    if r["source"] == "curated":
        return "curated"
    if "us.fundsforngos.org/type-of-grant" in u:
        return "us"
    if "fundsforngos.org/how-to-apply/" in u:
        return "international"
    if r["source"] in ("ictworks", "impact-catalyst") and r.get("relevant") and LEAD_TITLE.search(r["name"]):
        return "lead"
    return "skip"


def hai_relevant(r):
    return (section(r) in ("curated", "us", "lead") and r["status"] != "closed" and r.get("relevant")
            and (r.get("state") or "") in HAI_STATES)


def topics_of(r):
    return [t for t in r.get("tags", []) if ">" not in t and t not in META_TAGS]


# ---------- markdown ----------

def cell(s):
    return re.sub(r"\s+", " ", (s or "").replace("|", "/")).strip()


def link(r):
    return "[%s](%s)" % (cell(r["name"]).replace("[", "(").replace("]", ")"), r["url"])


def when(r):
    if r["deadline"]:
        return ("Closed " if r["status"] == "closed" else "") + r["deadline"]
    return "Rolling or not stated"


def table(rows, cols):
    head = {"when": "Deadline", "name": "Opportunity", "funder": "Funder", "amount": "Amount", "state": "Where", "check": "Checked"}
    cellf = {"when": when, "name": link, "funder": lambda r: cell(r["funder"]), "amount": lambda r: cell(r["amount_text"]),
             "state": lambda r: cell(r["state"]) or "-", "check": lambda r: "funder page read" if r["verified"] else "not yet"}
    lines = ["| " + " | ".join(head[c] for c in cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(cellf[c](r) for c in cols) + " |" for r in rows]
    return "\n".join(lines)


def by_deadline(rows):
    return sorted(rows, key=lambda r: (r["deadline"] is None, r["deadline"] or "", r["name"].lower()))


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def write(path, text):
    os.makedirs(os.path.dirname(os.path.join(ROOT, path)), exist_ok=True)
    with open(os.path.join(ROOT, path), "w", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")


NOTE = ("Listings are leads, not endorsements or awards. Rows marked \"not yet\" come from aggregator sites: "
        "read the funder's own page before applying.")


def render(store):
    rows = [dict(r, section=section(r)) for r in store.values()]
    shown = [r for r in rows if r["section"] != "skip"]
    opened = [r for r in shown if r["status"] != "closed"]
    us_dated = by_deadline([r for r in opened if r["section"] in ("us", "curated") and r["deadline"]])
    rolling = by_deadline([r for r in opened if r["section"] in ("us", "curated") and not r["deadline"]])
    intl = [r for r in opened if r["section"] == "international"]
    leads = [r for r in opened if r["section"] == "lead"]
    closed = sorted([r for r in shown if r["status"] == "closed"], key=lambda r: r["deadline"] or "", reverse=True)
    hai = [r for r in opened if hai_relevant(r)]
    stamp = today().isoformat()

    write("README.md", f"""# Nonprofit grants

An open list of small grants, technology credits and fellowships that a nonprofit could apply for. It is
not limited to one organization: most rows will not fit you, and some will fit well. Updated {stamp}.

{NOTE} Dates are sponsor deadlines as listed by the source. This list does not
apply for anything on anyone's behalf.

**{len(us_dated)}** open with a deadline · **{len(rolling)}** rolling or no deadline stated · **{len(intl)}** international ·
**{len(leads)}** leads from news sources · **{len(closed)}** closed (kept for next year's cycle).

Humanitarians AI keeps its own shortlist in [hai-grants](https://github.com/nikbearbrown/hai-grants); the rows
that fit its work ({len(hai)} today) are in [data/hai-relevant.json](data/hai-relevant.json).

## Open now, soonest deadline first

{table(us_dated, ["when", "name", "funder", "amount", "state", "check"])}

## Browse another way

- [Rolling or no deadline stated]({"lists/rolling.md"}) ({len(rolling)}): credits, programs and calls with no posted date
- [By topic](topics/README.md): education, health, arts, technology and more
- [By state](lists/by-state.md): where the funder or program is based, for state and local programs
- [International](lists/international.md) ({len(intl)}): calls from outside the US; deadlines not parsed
- [Leads from news sources](lists/leads.md) ({len(leads)}): articles about funding, not applications
- [Closed](lists/closed.md) ({len(closed)}): past deadlines, useful for planning next cycle
- [Funder locations](data/funder-locations.json): a pilot of addresses and coordinates for funders, all unreviewed
- Raw data: [data/opportunities.json](data/opportunities.json), [data/opportunities.csv](data/opportunities.csv)

## Where the rows come from

Public feeds from fundsforNGOs (US), ICTworks and Impact Catalyst, plus a hand-curated file
([curated.json](curated.json)). `checked` means a person read the funder's own page; everything else is a lead.
The collector is [nonprofit_grants.py](nonprofit_grants.py); sources are in [sources.json](sources.json).
To suggest a grant or correct a row, [open an issue](https://github.com/nikbearbrown/nonprofit-grants/issues/new)
(see [CONTRIBUTING.md](CONTRIBUTING.md)).

## License

Code: [MIT](LICENSE). Lists and data: [CC BY 4.0](LICENSE-DATA.md), so you may reuse them with credit.
The sources named above keep their own rights in their own text.
""")

    write("lists/rolling.md", f"# Rolling or no deadline stated\n\n{NOTE}\n\n{table(rolling, ['name', 'funder', 'amount', 'state', 'check'])}\n")
    write("lists/international.md", f"# International\n\nCalls listed outside the US. Deadlines are not parsed from the source: open each link.\n\n{NOTE}\n\n"
          + table(sorted(intl, key=lambda r: r["name"].lower()), ["name", "funder", "amount"]) + "\n")
    write("lists/leads.md", f"# Leads from news sources\n\nArticles and newsletters that mention funding relevant to AI, technology or humanitarian work. They link to an article, not an application.\n\n"
          + table(sorted(leads, key=lambda r: r["name"].lower()), ["name", "funder", "amount"]) + "\n")
    write("lists/closed.md", f"# Closed\n\nPast deadlines. Many programs repeat every year.\n\n"
          + table(closed, ["when", "name", "funder", "amount", "state"]) + "\n")

    states = {}
    for r in opened:
        if r["section"] in ("us", "curated") and r["state"] and r["state"] != "All States":
            states.setdefault(r["state"], []).append(r)
    body = "\n\n".join(f"## {s}\n\n{table(by_deadline(v), ['when', 'name', 'funder', 'amount'])}" for s, v in sorted(states.items()))
    write("lists/by-state.md", f"# By state\n\nOpen programs tied to one state. Programs open in every state are in the [main list](../README.md).\n\n{body}\n")

    tmap = {}
    for r in opened:
        if r["section"] in ("us", "curated"):
            for t in topics_of(r):
                tmap.setdefault(t, []).append(r)
    big = {t: v for t, v in tmap.items() if len(v) >= 5}
    for t, v in big.items():
        write(f"topics/{slug(t)}.md", f"# {t}\n\n{NOTE}\n\n{table(by_deadline(v), ['when', 'name', 'funder', 'amount', 'state'])}\n")
    idx = "\n".join(f"- [{t}]({slug(t)}.md) ({len(v)})" for t, v in sorted(big.items(), key=lambda kv: -len(kv[1])))
    write("topics/README.md", f"# By topic\n\nTopics come from the source's own tags; a grant can appear under several.\n\n{idx}\n")

    cols = ["id", "name", "funder", "url", "section", "source", "deadline", "status", "amount_text", "eligibility", "state",
            "tags", "verified", "first_seen", "last_seen", "hai_relevant"]
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "opportunities.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in sorted(shown, key=lambda r: (r["deadline"] or "9999", r["name"])):
            w.writerow([("; ".join(r["tags"]) if c == "tags" else hai_relevant(r) if c == "hai_relevant" else r.get(c, "")) for c in cols])
    with open(os.path.join(DATA, "hai-relevant.json"), "w", encoding="utf-8") as f:
        json.dump(by_deadline(hai), f, indent=1, ensure_ascii=False)
    return {"open_dated": len(us_dated), "rolling": len(rolling), "international": len(intl), "leads": len(leads),
            "closed": len(closed), "hai": len(hai), "topics": len(big), "states": len(states)}


def run(args):
    cfg = load_json(os.path.join(ROOT, "sources.json"))
    store = load_json(STORE, {})
    if args.cmd == "run":
        fresh, report = curated_rows(), []
        for feed in cfg["feeds"]:
            try:
                got = parse_feed(fetch(feed["url"], cfg["user_agent"]), feed["id"], feed["kind"], cfg)
                fresh += got
                report.append("%s: %d items" % (feed["id"], len(got)))
            except Exception as e:  # one dead feed must not stop the run
                report.append("%s: FAILED %s: %s" % (feed["id"], type(e).__name__, e))
        before = len(store)
        store = merge(store, fresh)
        report.append("stored %d (%d new)" % (len(store), len(store) - before))
        print("\n".join(report))
    else:
        store = merge(store, [])
    os.makedirs(DATA, exist_ok=True)
    with open(STORE, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=1, sort_keys=True, ensure_ascii=False)
    print("rendered:", render(store))
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["run", "render"])
    sys.exit(run(p.parse_args()))
