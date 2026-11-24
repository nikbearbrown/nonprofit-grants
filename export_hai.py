#!/usr/bin/env python3
"""Write the Humanitarians AI watchlist into a checkout of github.com/nikbearbrown/hai-grants.

    python3 export_hai.py /path/to/hai-grants

Reads data/hai-relevant.json (made by nonprofit_grants.py) and writes watchlist/README.md there.
Nothing else in that repo is touched.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nonprofit_grants as ng  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))


def main(dest):
    rows = json.load(open(os.path.join(ROOT, "data", "hai-relevant.json"), encoding="utf-8"))
    body = ng.table(rows, ["when", "name", "funder", "amount", "check"])
    text = f"""# Opportunities we are watching

Generated {ng.today().isoformat()} from [nonprofit-grants](https://github.com/nikbearbrown/nonprofit-grants), a public list of
grants for any nonprofit. These are the rows that match Humanitarians AI's work (AI, humanitarian and nonprofit technology) and
are open to a Massachusetts or national applicant.

**These are leads, not plans.** A listing here is not an application, an award or a commitment to apply. Rows marked "not yet"
come from aggregator sites, and the funder's own page has not been read. Our considered opportunities are in the [main table](../README.md).

{body}

Know of one we missed? [Open an issue](https://github.com/nikbearbrown/hai-grants/issues/new) or suggest it at
[nonprofit-grants](https://github.com/nikbearbrown/nonprofit-grants/issues/new).
"""
    os.makedirs(os.path.join(dest, "watchlist"), exist_ok=True)
    with open(os.path.join(dest, "watchlist", "README.md"), "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote", len(rows), "rows to", os.path.join(dest, "watchlist", "README.md"))


if __name__ == "__main__":
    main(sys.argv[1])
