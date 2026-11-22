"""Markdown -> sanitised HTML. Single renderer used by public pages, admin
previews and the AI chat so output is identical everywhere.

Syntax highlighting, language labels and copy buttons are added client side
(highlight.js) on top of the `<pre><code class="language-x">` markup produced
here. Sanitisation uses nh3 (Rust `ammonia`), so stored Markdown can never
inject scripts, event handlers or javascript: URLs.
"""
import html
import re

try:
    import markdown as _md
except ImportError:  # pragma: no cover
    _md = None
try:
    import nh3
except ImportError:  # pragma: no cover
    nh3 = None

from markupsafe import Markup

ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "code", "dd", "del", "div", "dl", "dt",
    "em", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "input", "ins",
    "kbd", "li", "mark", "ol", "p", "pre", "s", "small", "span", "strong", "sub",
    "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul", "figure",
    "figcaption", "details", "summary",
}
ALLOWED_ATTRS = {
    "*": {"class", "id", "title"},
    "a": {"href"},
    "img": {"src", "alt", "width", "height", "loading"},
    "input": {"type", "checked", "disabled"},
    "td": {"align", "colspan", "rowspan"},
    "th": {"align", "colspan", "rowspan"},
    "ol": {"start"},
    "abbr": {"title"},
}

_TASK_RE = re.compile(r"<li>(\s*<p>)?\s*\[([ xX])\]\s+")


def _tasklists(rendered):
    def repl(m):
        checked = " checked" if m.group(2).lower() == "x" else ""
        para = m.group(1) or ""
        return f'<li class="task-item">{para}<input type="checkbox" disabled{checked}> '

    out = _TASK_RE.sub(repl, rendered)
    return out.replace("<ul>\n<li class=\"task-item\">", "<ul class=\"task-list\">\n<li class=\"task-item\">")


def render_markdown(text):
    """Return safe HTML (Markup) for a Markdown string."""
    text = text or ""
    if not text.strip():
        return Markup("")
    if _md is None:
        rendered = "<p>" + html.escape(text).replace("\n", "<br>") + "</p>"
    else:
        rendered = _md.markdown(
            text,
            extensions=["extra", "sane_lists", "toc"],
            extension_configs={"toc": {"permalink": False}},
            output_format="html",
        )
        rendered = _tasklists(rendered)
    if nh3 is None:  # never emit unsanitised HTML: fall back to escaped paragraphs
        paras = [p.strip() for p in text.split("\n\n") if p.strip()]
        return Markup("".join("<p>" + html.escape(p).replace("\n", "<br>") + "</p>" for p in paras))
    attrs = {k: set(v) for k, v in ALLOWED_ATTRS.items()}
    star = attrs.pop("*")
    for tag in ALLOWED_TAGS:
        attrs.setdefault(tag, set()).update(star)
    clean = nh3.clean(
        rendered,
        tags=ALLOWED_TAGS,
        attributes=attrs,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer nofollow",
    )
    return Markup(clean)


def markdown_excerpt(text, n=220):
    """Plain-text excerpt (Markdown syntax stripped)."""
    text = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[#>*_`~|\-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"
