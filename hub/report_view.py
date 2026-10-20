"""Render a project's REPORT.md as a styled HTML page for the showcase hub (standard library only).

Covers the Markdown the reports use: headings, paragraphs, bold/italic/code, links, images,
bullet and numbered lists (one level of nesting), tables, block quotes, rules and fenced code.
```mermaid blocks are drawn with mermaid.js when tools/node_modules has it (served by the hub
at /vendor/mermaid.min.js), otherwise shown as source.
"""
import html
import re

_EMPHASIS = [
    (re.compile(r"\*\*([^*]+)\*\*"), r"<strong>\1</strong>"),
    (re.compile(r"(?<![\w*])\*([^*\s][^*]*)\*(?![\w*])"), r"<em>\1</em>"),
    (re.compile(r"(?<!\w)_([^_\s][^_]*)_(?!\w)"), r"<em>\1</em>"),
]


def inline(text, asset):
    """Inline Markdown -> HTML. Code spans are protected first so their contents stay literal."""
    codes = []

    def keep(m):
        codes.append("<code>%s</code>" % html.escape(m.group(1)))
        return "\x00%d\x00" % (len(codes) - 1)

    text = re.sub(r"`([^`]+)`", keep, text)
    text = html.escape(text, quote=False)

    def img(m):
        return '<img src="%s" alt="%s" loading="lazy">' % (html.escape(asset(m.group(2))), html.escape(m.group(1)))

    def link(m):
        href = m.group(2)
        if not re.match(r"[a-z]+:|#|/", href):
            href = asset(href)
        return '<a href="%s">%s</a>' % (html.escape(href), m.group(1))

    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", img, text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)
    for rx, repl in _EMPHASIS:
        text = rx.sub(repl, text)
    return re.sub("\x00(\\d+)\x00", lambda m: codes[int(m.group(1))], text)


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"<[^>]+>", "", text).lower()).strip("-")


def _cells(row):
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", row)]


def render_markdown(text, asset=lambda p: p):
    """Markdown -> (html, toc) where toc is [(level, anchor, title)] for ## and ### headings."""
    lines = text.replace("\r\n", "\n").split("\n")
    out, toc, para = [], [], []
    i = 0

    def flush():
        if para:
            out.append("<p>%s</p>" % inline(" ".join(para), asset))
            para.clear()

    while i < len(lines):
        line = lines[i]
        s = line.strip()
        fence = re.match(r"^(```|~~~)\s*([\w-]*)", s)
        if fence:
            flush()
            lang, body = fence.group(2), []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(fence.group(1)):
                body.append(lines[i])
                i += 1
            code = html.escape("\n".join(body))
            if lang == "mermaid":
                out.append('<figure class="diagram"><pre class="mermaid">%s</pre></figure>' % code)
            else:
                out.append('<pre><code class="lang-%s">%s</code></pre>' % (html.escape(lang or "text"), code))
            i += 1
            continue
        h = re.match(r"^(#{1,6})\s+(.*?)\s*#*$", s)
        if h:
            flush()
            level, title = len(h.group(1)), inline(h.group(2), asset)
            anchor = _slug(title)
            if level in (2, 3):
                toc.append((level, anchor, html.unescape(re.sub(r"<[^>]+>", "", title))))
            out.append('<h%d id="%s">%s</h%d>' % (level, anchor, title, level))
            i += 1
            continue
        if re.match(r"^(\*\s*\*\s*\*|-\s*-\s*-|_\s*_\s*_)[\s*_-]*$", s):
            flush()
            out.append("<hr>")
            i += 1
            continue
        if s.startswith("|") and i + 1 < len(lines) and re.match(r"^\|?\s*:?-{2,}", lines[i + 1].strip()):
            flush()
            head = _cells(s)
            aligns = ["right" if c.endswith(":") and not c.startswith(":") else "center" if c.startswith(":") and c.endswith(":") else ""
                      for c in _cells(lines[i + 1])]
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1

            def td(tag, c, k):
                a = aligns[k] if k < len(aligns) and aligns[k] else ""
                return "<%s%s>%s</%s>" % (tag, ' style="text-align:%s"' % a if a else "", inline(c, asset), tag)

            out.append('<div class="table-wrap"><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>' % (
                "".join(td("th", c, k) for k, c in enumerate(head)),
                "".join("<tr>%s</tr>" % "".join(td("td", c, k) for k, c in enumerate(r)) for r in rows)))
            continue
        if s.startswith(">"):
            flush()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            inner, _ = render_markdown("\n".join(quote), asset)
            out.append("<blockquote>%s</blockquote>" % inner)
            continue
        item = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", line)
        if item:
            flush()
            block, i = _list(lines, i, asset)
            out.append(block)
            continue
        if not s:
            flush()
        else:
            para.append(s)
        i += 1
    flush()
    return "\n".join(out), toc


def _list(lines, i, asset):
    """The list starting at lines[i] -> (html, index after it). Deeper-indented items nest."""
    first = re.match(r"^(\s*)([-*+]|\d+[.)])\s+", lines[i])
    indent, ordered = len(first.group(1)), first.group(2)[0].isdigit()
    start = int(first.group(2)[:-1]) if ordered else 1
    items = []
    while i < len(lines):
        m = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", lines[i])
        if m and len(m.group(1)) == indent and m.group(2)[0].isdigit() == ordered:
            items.append([m.group(3), ""])
            i += 1
        elif m and len(m.group(1)) > indent and items:
            sub, i = _list(lines, i, asset)
            items[-1][1] += sub
        elif lines[i].strip() and items and not m and len(lines[i]) - len(lines[i].lstrip()) > indent:
            items[-1][0] += " " + lines[i].strip()  # wrapped continuation line
            i += 1
        else:
            break
    tag = "ol" if ordered else "ul"
    attrs = ' start="%d"' % start if ordered and start != 1 else ""
    return "<%s%s>%s</%s>" % (tag, attrs, "".join("<li>%s%s</li>" % (inline(t, asset), sub) for t, sub in items), tag), i


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} report · QUANTIX 2K26</title>
<style>
  :root {{ --accent: {color}; --bg: #f4f5fb; --card: #fff; --ink: #11162e; --muted: #5b6180; --line: #e2e4f0; --code: #f0f2f8; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg: #0b1026; --card: #141a37; --ink: #eceffa; --muted: #a5abc9; --line: #2a3260; --code: #1b2246; }} }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.65 system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans Tamil", sans-serif; }}
  header {{ position: sticky; top: 0; z-index: 2; display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
           padding: 12px 20px; background: var(--card); border-bottom: 1px solid var(--line); border-top: 4px solid var(--accent); }}
  header b {{ font-size: 17px; }}
  header .sp {{ flex: 1; }}
  .btn {{ font-weight: 600; font-size: 14px; text-decoration: none; color: var(--ink); border: 1px solid var(--line);
         border-radius: 9px; padding: 6px 14px; background: var(--card); }}
  .btn:hover, .btn:focus-visible {{ border-color: var(--accent); outline: none; }}
  .btn.primary {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
  .wrap {{ max-width: 1180px; margin: 0 auto; padding: 24px 20px 48px; display: grid; grid-template-columns: 240px minmax(0, 1fr); gap: 28px; }}
  nav.toc {{ position: sticky; top: 76px; align-self: start; font-size: 14px; max-height: calc(100vh - 96px); overflow: auto; }}
  nav.toc a {{ display: block; color: var(--muted); text-decoration: none; padding: 3px 0 3px 10px; border-left: 2px solid var(--line); }}
  nav.toc a.l3 {{ padding-left: 22px; font-size: 13px; }}
  nav.toc a:hover {{ color: var(--ink); border-left-color: var(--accent); }}
  article {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 28px 36px; min-width: 0; }}
  h1 {{ font-size: 32px; line-height: 1.2; margin: 0 0 8px; }}
  h2 {{ font-size: 23px; margin: 36px 0 10px; padding-top: 10px; border-top: 1px solid var(--line); scroll-margin-top: 80px; }}
  h3 {{ font-size: 18px; margin: 24px 0 8px; scroll-margin-top: 80px; }}
  a {{ color: var(--accent); }}
  img {{ max-width: 100%; height: auto; border-radius: 10px; border: 1px solid var(--line); }}
  code {{ background: var(--code); border-radius: 6px; padding: 1px 6px; font-size: .9em; }}
  pre {{ background: var(--code); border-radius: 10px; padding: 14px 16px; overflow-x: auto; font-size: 14px; line-height: 1.5; }}
  pre code {{ background: none; padding: 0; }}
  figure.diagram {{ margin: 16px 0; text-align: center; }}
  figure.diagram pre {{ text-align: left; }}
  figure.diagram svg {{ max-width: 100%; height: auto; }}
  .table-wrap {{ overflow-x: auto; margin: 14px 0; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 15px; }}
  th, td {{ border-bottom: 1px solid var(--line); padding: 8px 10px; text-align: left; vertical-align: top; }}
  th {{ font-size: 13px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }}
  blockquote {{ margin: 16px 0; padding: 10px 18px; border-left: 4px solid var(--accent); background: var(--code); border-radius: 0 10px 10px 0; }}
  blockquote p {{ margin: 6px 0; }}
  hr {{ border: 0; border-top: 1px solid var(--line); margin: 28px 0; }}
  @media (max-width: 900px) {{ .wrap {{ grid-template-columns: minmax(0, 1fr); padding: 16px; }} nav.toc {{ display: none; }} article {{ padding: 20px 18px; }} h1 {{ font-size: 26px; }} }}
</style></head><body>
<header><b>{name}</b><span style="color:var(--muted)">{tagline}</span><span class="sp"></span>
  <a class="btn" href="/">← All projects</a>{demo}</header>
<div class="wrap"><nav class="toc" aria-label="Sections">{toc}</nav><article>{body}</article></div>
{mermaid}
</body></html>
"""

MERMAID = """<script src="/vendor/mermaid.min.js"></script>
<script>
  if (window.mermaid) {
    const dark = matchMedia("(prefers-color-scheme: dark)").matches;
    mermaid.initialize({ startOnLoad: false, theme: dark ? "dark" : "neutral", securityLevel: "strict" });
    mermaid.run({ querySelector: "pre.mermaid" }).catch(() => {});
  }
</script>"""


def report_page(pitch, markdown, asset, demo_url=None, have_mermaid=False):
    body, toc = render_markdown(markdown, asset)
    toc_html = "".join('<a class="l%d" href="#%s">%s</a>' % (lvl, a, html.escape(t)) for lvl, a, t in toc)
    demo = '<a class="btn primary" href="%s" target="_blank" rel="noopener">Open demo</a>' % html.escape(demo_url) if demo_url else ""
    color = pitch.get("color", "#6C4CF1")
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        color = "#6C4CF1"
    return PAGE.format(name=html.escape(pitch.get("name", "Report")), tagline=html.escape(pitch.get("tagline", "")),
                       color=color, demo=demo, toc=toc_html, body=body,
                       mermaid=MERMAID if have_mermaid and "pre class=\"mermaid\"" in body else "")
