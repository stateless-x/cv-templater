"""Check a built CV the way an ATS reads it.

Usage:  python check.py examples/example.yaml path/to/built.pdf
Needs pdftotext and pdfinfo (poppler: `brew install poppler` or `apt install poppler-utils`).
Exits 1 if any check fails.
"""
import re
import subprocess
import sys

import yaml

cv = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
pdf = sys.argv[2]
text = subprocess.run(["pdftotext", pdf, "-"], capture_output=True, text=True, check=True).stdout
info = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True, check=True).stdout
pages = int(re.search(r"Pages:\s+(\d+)", info).group(1))
rules = cv.get("checks", {})
max_pages = rules.get("max_pages", 2)

checks = {
    f"at most {max_pages} pages (has {pages})": pages <= max_pages,
    "name is the first text": text.lstrip().startswith(cv["name"]),
}
for item in cv.get("contact", []) + cv.get("links", []):
    checks[f"extracts: {item}"] = str(item) in text
jobs = [j for s in cv.get("sections", []) for j in s.get("jobs", [])]
for job in jobs:
    # Company and dates on one line, so parsers pair them correctly.
    line = re.search(rf"^{re.escape(job['company'])}.*{re.escape(job['dates'])}\s*$", text, re.M)
    checks[f"job line: {job['company']} with {job['dates']}"] = bool(line)
for s in cv.get("sections", []):
    checks[f"heading: {s['title']}"] = bool(re.search(rf"^{re.escape(s['title'])}\s*$", text, re.M | re.I))

found = [w for w in rules.get("banned_terms", []) if re.search(rf"\b{re.escape(w)}\b", text, re.I)]
checks["no banned terms" + (f" (found: {', '.join(found)})" if found else "")] = not found
checks["no leftover [placeholders]"] = "[" not in text and "**" not in text

for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
failed = [n for n, ok in checks.items() if not ok]
print(f"\n{len(checks) - len(failed)}/{len(checks)} passed")
sys.exit(1 if failed else 0)
