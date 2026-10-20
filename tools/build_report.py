"""Build the combined QUANTIX 2K26 report: one HTML file, then a PDF.

    python tools/build_report.py              # -> build/QUANTIX2K26_Report.html and .pdf
    python tools/build_report.py --html-only

Needs pandoc on PATH (Markdown -> HTML) and, for the PDF, Node with Playwright plus
`cd tools && npm install` (for mermaid). Sections: cover, contents, strategy,
portfolio overview, then every project's REPORT.md with its screenshot.
"""
import datetime
import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"

DOMAIN_ORDER = ["Artificial", "Sustainability", "HealthTech", "Cybersecurity", "Smart", "Data"]
DOMAIN_SHORT = {
    "Artificial": "AI & ML", "Sustainability": "Sustainability", "HealthTech": "HealthTech",
    "Cybersecurity": "Cyber & Blockchain", "Smart": "AgriTech & Rural", "Data": "Data Science",
}


def domain_key(domain):
    first = re.sub(r"[^A-Za-z]", "", domain.split(" ")[0])
    return DOMAIN_ORDER.index(first) if first in DOMAIN_ORDER else len(DOMAIN_ORDER), DOMAIN_SHORT.get(first, domain)


def md_to_html(text, base_dir):
    """Markdown -> HTML fragment via pandoc; relative image paths become absolute file URIs."""
    out = subprocess.run(
        ["pandoc", "-f", "gfm", "-t", "html5", "--no-highlight"],
        input=text, capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout

    def fix_src(m):
        src = m.group(1)
        if re.match(r"^(https?:|data:|file:)", src):
            return m.group(0)
        return 'src="%s"' % (base_dir / src).resolve().as_uri()

    out = re.sub(r'src="([^"]+)"', fix_src, out)
    # pandoc emits mermaid blocks as <pre class="mermaid"><code>...</code></pre>
    out = re.sub(r'<pre class="mermaid"><code>(.*?)</code></pre>',
                 r'<div class="mermaid">\1</div>', out, flags=re.S)
    # links to other repo files are dead inside a PDF; keep the text
    out = re.sub(r'<a href="(?!https?:|#)[^"]*">(.*?)</a>', r"\1", out, flags=re.S)
    return out


def demote_headings(fragment, slug):
    """Project reports use # / ## headings; nest them under the project's own h1 and namespace ids."""
    fragment = re.sub(r"<h1([^>]*)>.*?</h1>", "", fragment, count=1, flags=re.S)  # replaced by our banner
    for level in (5, 4, 3, 2, 1):
        fragment = re.sub(r"<(/?)h%d([ >])" % level, r"<\1h%d\2" % min(level + 1, 6), fragment)
    return re.sub(r'id="([^"]+)"', lambda m: 'id="%s-%s"' % (slug, m.group(1)), fragment)


def load_projects():
    items = []
    for d in sorted((ROOT / "projects").iterdir()):
        pj, rep = d / "pitch.json", d / "REPORT.md"
        if not (pj.exists() and rep.exists()):
            continue
        pitch = json.loads(pj.read_text(encoding="utf-8"))
        order, short = domain_key(pitch.get("domain", ""))
        items.append({"dir": d, "slug": d.name, "num": d.name.split("-")[0], "pitch": pitch,
                      "order": order, "short": short})
    return sorted(items, key=lambda p: (p["order"], p["num"]))


def esc(s):
    return html.escape(str(s))


def build_html(team):
    projects = load_projects()
    strategy = (ROOT / "docs" / "STRATEGY.md").read_text(encoding="utf-8")
    test_total = 0
    for p in projects:
        for f in (p["dir"] / "tests").glob("test_*.py"):
            test_total += len(re.findall(r"^\s+def test_", f.read_text(encoding="utf-8"), flags=re.M))

    today = datetime.date.today().strftime("%d %B %Y")
    members = ", ".join(team.get("members") or []) or ""
    parts = []

    # cover
    parts.append(f"""
<section class="cover">
  <div class="eyebrow">QUANTIX 2K26 · 24-hour hackathon · K.S.R. College of Engineering</div>
  <h1 class="title">Project Portfolio &amp; Hackathon Reports</h1>
  <p class="lede">{len(projects)} working, offline-first prototypes across all six hackathon domains, with
  architecture, algorithms, measured results, demo scripts and judges' Q&amp;A for each.</p>
  <div class="stats">
    <div><b>{len(projects)}</b><span>prototypes</span></div>
    <div><b>6</b><span>domains</span></div>
    <div><b>{test_total:,}</b><span>unit tests</span></div>
    <div><b>0</b><span>pip installs</span></div>
  </div>
  <div class="team"><b>{esc(team.get("team", ""))}</b>{(" · " + esc(members)) if members else ""}<br>
  Code: {esc(team.get("github", ""))} (branch {esc(team.get("branch", "main"))}) · {today}</div>
</section>""")

    # contents
    rows = []
    for p in projects:
        rows.append(f'<li><a href="#p-{p["slug"]}"><span class="num">{p["num"]}</span> '
                    f'<b>{esc(p["pitch"]["name"])}</b> <span class="dom">{esc(p["short"])}</span>'
                    f'<span class="tag">{esc(p["pitch"].get("tagline", ""))}</span></a></li>')
    parts.append(f"""
<section class="toc">
  <h1>Contents</h1>
  <ol class="toc-main">
    <li><a href="#strategy"><b>Part 1 · Winning strategy and playbook</b></a></li>
    <li><a href="#overview"><b>Part 2 · Portfolio overview</b></a></li>
    <li><a href="#projects"><b>Part 3 · Project reports</b></a>
      <ol class="toc-projects">{''.join(rows)}</ol></li>
  </ol>
</section>""")

    # part 1
    strat_html = md_to_html(strategy, ROOT / "docs")
    strat_html = re.sub(r"<h1[^>]*>.*?</h1>", "", strat_html, count=1, flags=re.S)
    parts.append(f'<section class="part" id="strategy"><div class="part-label">Part 1</div>'
                 f'<h1>Winning strategy and playbook</h1>{strat_html}</section>')

    # part 2
    trs = []
    for p in projects:
        res = "".join(f"<li><b>{esc(r['value'])}</b> {esc(r['label'])}</li>" for r in p["pitch"].get("results", [])[:3])
        trs.append(f'<tr><td class="num">{p["num"]}</td><td><b style="color:{esc(p["pitch"].get("color", "#333"))}">'
                   f'{esc(p["pitch"]["name"])}</b><br><span class="small">{esc(p["pitch"].get("tagline", ""))}</span></td>'
                   f'<td>{esc(p["short"])}</td><td><ul class="res">{res}</ul></td></tr>')
    parts.append(f"""
<section class="part" id="overview"><div class="part-label">Part 2</div><h1>Portfolio overview</h1>
<p>Every project runs with <code>python app.py</code> (Python 3.9+ standard library only, no internet),
has its own unit tests, a full report (Part 3) and a generated 11-slide pitch deck in <code>decks/</code>.
All data is synthetic and generated by each project's own seeded code, so the results below show the
implementation works; they are not field measurements.</p>
<table class="overview"><thead><tr><th>#</th><th>Project</th><th>Domain</th><th>Headline results</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table></section>""")

    # part 3
    parts.append('<section class="part divider" id="projects"><div class="part-label">Part 3</div>'
                 '<h1>Project reports</h1><p>One chapter per project, in domain order. Each follows the same '
                 '15-section template: problem, solution, innovation, architecture, algorithms, tech stack, '
                 'results, screenshot, demo script, impact, business model, future scope, judges\' Q&amp;A and how to run.</p></section>')
    for p in projects:
        pitch = p["pitch"]
        body = md_to_html((p["dir"] / "REPORT.md").read_text(encoding="utf-8"), p["dir"])
        body = demote_headings(body, p["slug"])
        shot = p["dir"] / "docs" / "screenshot.png"
        hero = f'<img class="hero" src="{shot.resolve().as_uri()}" alt="{esc(pitch["name"])} screenshot">' if shot.exists() else ""
        color = esc(pitch.get("color", "#333333"))
        parts.append(f"""
<section class="project" id="p-{p['slug']}" style="--brand:{color}">
  <div class="banner"><span class="pnum">#{p['num']} · {esc(p['short'])} · port {esc(pitch.get('port', ''))}</span>
    <h1>{esc(pitch['name'])}</h1><p class="ptag">{esc(pitch.get('tagline', ''))}</p></div>
  {hero}
  <div class="report">{body}</div>
</section>""")

    css = (Path(__file__).resolve().parent / "report.css").read_text(encoding="utf-8")
    # Tamil text needs a font with Tamil shaping; use the npm copy of Noto Sans Tamil when present
    fonts = Path(__file__).resolve().parent / "node_modules" / "@fontsource" / "noto-sans-tamil" / "files"
    for weight in (400, 700):
        woff = fonts / f"noto-sans-tamil-tamil-{weight}-normal.woff2"
        if woff.exists():
            css = (f'@font-face {{ font-family: "Noto Sans Tamil"; font-weight: {weight}; '
                   f'src: url("{woff.as_uri()}") format("woff2"); unicode-range: U+0B80-0BFF; }}\n') + css
    mermaid = Path(__file__).resolve().parent / "node_modules" / "mermaid" / "dist" / "mermaid.min.js"
    mermaid_tag = f'<script src="{mermaid.as_uri()}"></script>' if mermaid.exists() else ""
    def page(body, script=""):
        return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<title>QUANTIX 2K26 Project Portfolio</title><style>{css}</style>{mermaid_tag}</head>'
                f'<body>{body}{script}</body></html>')

    diagram_script = """
<script>
window.__diagramsDone = false;
(async () => {
  const blocks = [...document.querySelectorAll('div.mermaid')];
  const esc = s => s.replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  if (window.mermaid) {
    mermaid.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'loose',
                         flowchart: { htmlLabels: true, useMaxWidth: true } });
    let i = 0;
    for (const el of blocks) {
      const src = el.textContent;
      try {
        const { svg } = await mermaid.render('mmd' + (i++), src);
        el.innerHTML = svg;
      } catch (e) {
        el.outerHTML = '<pre class="diagram-src">' + esc(src) + '</pre>';
      }
    }
  } else {
    blocks.forEach(el => { el.outerHTML = '<pre class="diagram-src">' + esc(el.textContent) + '</pre>'; });
  }
  window.__diagramsDone = true;
})();
</script>"""
    # the cover is rendered on its own (full-bleed, no margins) and joined to the body afterwards
    cover = page(parts[0], "<script>window.__diagramsDone = true;</script>")
    return cover, page("".join(parts[1:]), diagram_script)


def main(argv):
    team = {"team": "Your Team Name", "members": [], "github": "", "branch": "main"}
    tj = ROOT / "team.json"
    if tj.exists():
        team.update(json.loads(tj.read_text(encoding="utf-8")))
    BUILD.mkdir(exist_ok=True)
    cover, body = build_html(team)
    cover_html, body_html = BUILD / "report_cover.html", BUILD / "QUANTIX2K26_Report.html"
    cover_html.write_text(cover, encoding="utf-8")
    body_html.write_text(body, encoding="utf-8")
    print("wrote", body_html.relative_to(ROOT))
    if "--html-only" in argv:
        return 0
    out_pdf = BUILD / "QUANTIX2K26_Report.pdf"
    subprocess.run(["node", str(Path(__file__).resolve().parent / "report_pdf.js"),
                    str(cover_html), str(body_html), str(out_pdf)], check=True)
    print("wrote", out_pdf.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
