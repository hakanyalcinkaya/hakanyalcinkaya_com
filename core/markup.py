"""Kullanıcının yazdığı Markdown'ı güvenli HTML'e çevirir (ders ek içerikleri).

Markdown içinde HTML de yazılabilir; çıktı izinli etiket ve özniteliklere göre temizlenir (script, olay öznitelikleri,
javascript: bağlantıları atılır). Dış bağlantılar yeni sekmede açılır.
"""

import markdown
import nh3

ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "code", "dd", "del", "details", "div", "dl", "dt", "em", "figcaption",
    "figure", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "ins", "kbd", "li", "mark", "ol", "p", "pre", "s",
    "small", "span", "strong", "sub", "summary", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul",
}
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "abbr": {"title"},
    "img": {"src", "alt", "title", "width", "height"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
    "ol": {"start"},
    "code": {"class"},
}
MARKDOWN_EXTENSIONS = ["extra", "sane_lists"]


def render_markdown(text):
    if not text or not text.strip():
        return ""
    html = markdown.markdown(text, extensions=MARKDOWN_EXTENSIONS, output_format="html")
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer",
        set_tag_attribute_values={"a": {"target": "_blank"}},
    )
