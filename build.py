"""Build an ATS-friendly CV PDF from a YAML file and a theme.

Usage:  python build.py examples/example.yaml
Output: the path in the YAML's `output`, or output/<Name>_CV_<version>.pdf

Layout rules this engine keeps, so parsers and AI screeners read the CV correctly:
- One column of real text. Decoration (page colour, band, logo) is drawn on the
  canvas and never enters the text layer.
- Each job's dates sit on its company line, not in a right-hand column, so a
  parser cannot pair a date with the wrong job.
- Link text is shown as the address itself; parsers drop link targets.
- Non-Latin domains (e.g. ตัวอย่าง.com) are linked through their punycode form.
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parent


# ---------- inline text: escape, then **bold**, [text](url), and soft " | " ----------

SEP_COLOR = "#999999"  # set from the theme in build()

def to_url(target):
    """Turn 'example.com' or 'name@site.com' into a working href; punycode non-Latin hosts."""
    if "@" in target and not target.startswith(("http", "mailto:")):
        return "mailto:" + target
    if not re.match(r"^[a-z]+:", target):
        target = "https://" + target
    parts = urlsplit(target)
    host = parts.hostname or ""
    if host and not host.isascii():
        host = host.encode("idna").decode("ascii")
        target = parts._replace(netloc=host + (f":{parts.port}" if parts.port else "")).geturl()
    return target


def inline(text, link_color):
    text = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = text.replace(" | ", f'  <font color="{SEP_COLOR}">|</font>  ')
    return re.sub(r"\[(.+?)\]\((.+?)\)",
                  lambda m: f'<link href="{to_url(m.group(2))}" color="{link_color}">{m.group(1)}</link>', text)


def autolink(item, link_color):
    """Contact/link entries: link emails and domains, leave plain words alone."""
    item = str(item)
    if "@" in item or re.match(r"^[^\s]+\.[^\s]{2,}(/\S*)?$", item):
        return f'<link href="{to_url(item)}" color="{link_color}">{inline(item, link_color)}</link>'
    return inline(item, link_color)


# ---------- build ----------

def build(cv_path):
    cv_path = Path(cv_path).resolve()
    cv = yaml.safe_load(cv_path.read_text(encoding="utf-8"))
    theme_dir = ROOT / "themes" / cv.get("theme", "pooh")
    t = json.loads((theme_dir / "theme.json").read_text())
    C = {k: colors.HexColor(v) for k, v in t["colors"].items()}
    hexc = {k: v for k, v in t["colors"].items()}
    global SEP_COLOR
    SEP_COLOR = hexc["separator"]
    size, gap = t["sizes"], t["spacing"]

    for key, file in t["fonts"].items():
        pdfmetrics.registerFont(TTFont(f"{t['name']}-{key}", str(theme_dir / "fonts" / file)))
    F = {key: f"{t['name']}-{key}" for key in t["fonts"]}
    # Without a family mapping, <b> inside a paragraph silently renders regular.
    pdfmetrics.registerFontFamily(F["body"], normal=F["body"], bold=F["body_bold"],
                                  italic=F["body"], boldItalic=F["body_bold"])

    top, right, bottom, left = (v * mm for v in t["page"]["margin_mm"])
    page_w, page_h = A4
    content_w = page_w - left - right
    sep = f'  <font color="{hexc["separator"]}">|</font>  '
    link = hexc["ink"]

    def st(name, **kw):
        base = dict(fontName=F["body"], fontSize=size["body"], leading=size["body"] * 1.5, textColor=C["ink"])
        base.update(kw)
        return ParagraphStyle(name, **base)

    S = {
        "name": st("name", fontName=F["head_bold"], fontSize=size["name"], leading=size["name"] * 1.2, spaceAfter=2),
        "headline": st("headline", fontName=F["head"], fontSize=size["headline"], leading=size["headline"] * 1.33,
                       textColor=C["accent_ink"], spaceAfter=8),
        "contact": st("contact", fontSize=size["contact"], leading=size["contact"] * 1.5, textColor=C["muted"]),
        "section": st("section", fontName=F["head_bold"], fontSize=size["section"], leading=size["section"] * 1.2,
                      spaceBefore=gap["section_before"], spaceAfter=3),
        "body": st("body"),
        "role": st("role", fontName=F["head_medium"], fontSize=size["role"], leading=size["role"] * 1.3),
        "meta": st("meta", fontSize=size["meta"], leading=size["meta"] * 1.5, textColor=C["muted"], spaceAfter=3),
        "bullet": st("bullet", leftIndent=11, bulletIndent=1, spaceAfter=gap["between_bullets"],
                     bulletFontName=F["body"], bulletColor=C["accent"]),
        "tier": st("tier", fontName=F["body_bold"], fontSize=8.8, leading=12, textColor=C["accent_ink"], spaceAfter=3),
        "tier_next": st("tier_next", fontName=F["body_bold"], fontSize=8.8, leading=12, textColor=C["accent_ink"],
                        spaceBefore=8, spaceAfter=3),
        "skills_main": st("skills_main", fontSize=size["skills_main"], leading=size["skills_main"] * 1.5, spaceAfter=1.5),
        "skills_minor": st("skills_minor", fontSize=size["skills_minor"], leading=size["skills_minor"] * 1.5,
                           textColor=C["muted"], spaceAfter=1),
    }
    P = lambda text, s="body": Paragraph(text, S[s])
    bullet = lambda text: Paragraph(inline(text, link), S["bullet"], bulletText="•")

    def underline():
        return Table([[""]], colWidths=[gap["underline_mm"] * mm], rowHeights=[2.2], hAlign="LEFT",
                     style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), C["accent"])] +
                                      [(p, (0, 0), (-1, -1), 0) for p in
                                       ("LEFTPADDING", "RIGHTPADDING", "TOPPADDING", "BOTTOMPADDING")]))

    def heading(title):
        return [P(inline(title, link), "section"), underline(), Spacer(1, gap["section_after"])]

    story = [
        P(inline(cv["name"], link), "name"),
        P(inline(cv.get("headline", ""), link), "headline"),
    ]
    if cv.get("contact"):
        story.append(P(sep.join(autolink(c, link) for c in cv["contact"]), "contact"))
    if cv.get("links"):
        story.append(P(sep.join(autolink(c, link) for c in cv["links"]), "contact"))

    for sec in cv.get("sections", []):
        head = heading(sec["title"])
        if "jobs" in sec:  # experience-style: role, company line with dates, bullets
            story += head
            for job in sec["jobs"]:
                meta = f'<font name="{F["body_bold"]}" color="{hexc["accent_ink"]}">{inline(job["company"], link)}</font>'
                for extra in (job.get("about"), job.get("dates")):
                    if extra:
                        meta += sep + inline(extra, link)
                parts = [P(inline(job["role"], link), "role"), P(meta, "meta")]
                parts += [bullet(b) for b in job.get("bullets", [])]
                parts.append(Spacer(1, gap["between_jobs"]))
                story.append(KeepTogether(parts))
        elif "items" in sec:  # project-style: optional intro, then bullets
            block = head + ([P(inline(sec["intro"], link), "meta"), Spacer(1, 2)] if sec.get("intro") else [])
            items = [bullet(i) for i in sec["items"]]
            story.append(KeepTogether(block + items[:1]))  # never strand the heading
            story += items[1:]
        elif "tiers" in sec:  # skills: first tier full size, later tiers smaller
            story += head
            for n, tier in enumerate(sec["tiers"]):
                if tier.get("name"):
                    story.append(P(inline(tier["name"], link), "tier" if n == 0 else "tier_next"))
                minor = tier.get("minor", n > 0)
                label_font = F["body_medium"] if minor else F["body_bold"]
                for label, value in tier["rows"].items():
                    story.append(P(f'<font name="{label_font}">{inline(label, link)}:</font> {inline(value, link)}',
                                   "skills_minor" if minor else "skills_main"))
        elif "inline" in sec:  # short list on one line, e.g. spoken languages
            story += head + [P(sep.join(inline(x, link) for x in sec["inline"]))]
        else:
            story += head + [P(inline(sec.get("text", ""), link))]

    logo = cv.get("logo")
    logo_path = (cv_path.parent / logo).resolve() if logo else None

    def on_page(canvas, _doc):
        canvas.saveState()
        canvas.setFillColor(C["paper"])
        canvas.rect(0, 0, page_w, page_h, stroke=0, fill=1)
        if canvas.getPageNumber() == 1:
            band = t["page"]["band_mm"] * mm
            canvas.setFillColor(C["accent"])
            canvas.rect(0, page_h - band, page_w, band, stroke=0, fill=1)
            if logo_path:
                s = 17 * mm
                canvas.drawImage(str(logo_path), page_w - right - s, page_h - top - s + 1 * mm, s, s, mask="auto")
        canvas.restoreState()
        canvas.setTitle(f'{cv["name"]} | {cv.get("headline", "CV")}')
        canvas.setAuthor(cv["name"])
        canvas.setSubject(f'CV: {cv.get("headline", "")}')
        if cv.get("keywords"):
            canvas.setKeywords(", ".join(cv["keywords"]))

    default_name = f'{cv["name"].replace(" ", "_")}_CV_{cv.get("version", "latest")}.pdf'
    out = (cv_path.parent / cv["output"]).resolve() if cv.get("output") else ROOT / "output" / default_name
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(str(out), pagesize=A4, leftMargin=left, rightMargin=right, topMargin=top,
                          bottomMargin=bottom, title=cv["name"], author=cv["name"])
    frame = Frame(left, bottom, content_w, page_h - top - bottom, id="main",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)  # rules align with text
    doc.addPageTemplates([PageTemplate(id="cv", frames=[frame], onPage=on_page)])
    doc.build(story)
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python build.py path/to/cv.yaml")
    print(build(sys.argv[1]))
