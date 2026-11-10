"""HTML and URL sanitization helpers.

Course and lab authors can paste rich text. That content is rendered with the
``safe`` Jinja filter, so it must be sanitized both when it is stored and when
legacy rows are rendered. Markdown is rendered through the sanitized
``markdown`` filter instead of being trusted directly.
"""

import re

import bleach
import markdown as md_lib

# bleach removes dangerous tags but keeps their text content. For script,
# style, iframe and form blocks the content itself must be dropped too.
_DANGEROUS_BLOCKS = re.compile(
    r'<(script|style|iframe|object|embed|form|noscript)\b[^>]*>.*?</\1\s*>',
    re.IGNORECASE | re.DOTALL,
)

# Formatting, tables, code and images are enough for lesson notes. Scripts,
# forms, iframes, objects, styles and event handlers are never allowed.
ALLOWED_TAGS = frozenset({
    'a', 'abbr', 'b', 'blockquote', 'br', 'caption', 'code', 'col', 'colgroup',
    'del', 'div', 'em', 'figcaption', 'figure', 'h1', 'h2', 'h3', 'h4', 'h5',
    'h6', 'hr', 'i', 'img', 'ins', 'kbd', 'li', 'ol', 'p', 'pre', 's', 'span',
    'strong', 'sub', 'sup', 'table', 'tbody', 'td', 'tfoot', 'th', 'thead',
    'tr', 'u', 'ul',
})

ALLOWED_ATTRIBUTES = {
    '*': ['class', 'title'],
    'a': ['href', 'title', 'target', 'rel'],
    'img': ['src', 'alt', 'title', 'width', 'height', 'loading'],
    'col': ['span'],
    'colgroup': ['span'],
    'td': ['colspan', 'rowspan'],
    'th': ['colspan', 'rowspan'],
    'h1': ['id'],
    'h2': ['id'],
    'h3': ['id'],
    'h4': ['id'],
    'h5': ['id'],
    'h6': ['id'],
}

ALLOWED_PROTOCOLS = frozenset({'http', 'https', 'mailto'})

MARKDOWN_EXTENSIONS = ['fenced_code', 'tables', 'nl2br']


def sanitize_html(value):
    """Return ``value`` with unsafe markup, attributes and URLs removed."""
    if not value:
        return ''
    value = _DANGEROUS_BLOCKS.sub('', str(value))
    return bleach.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )


def sanitize_rich_content(value):
    """Sanitize HTML bodies while leaving Markdown source untouched.

    Markdown is escaped by ``render_markdown`` when it is displayed. Sanitizing
    raw Markdown with an HTML cleaner would corrupt blockquotes and code.
    """
    if not value:
        return value or ''
    if str(value).lstrip().startswith('<'):
        return sanitize_html(value)
    return value


def render_markdown(value):
    """Render Markdown and sanitize the generated HTML in one step."""
    if not value:
        return ''
    html = md_lib.markdown(str(value), extensions=MARKDOWN_EXTENSIONS)
    return sanitize_html(html)


def safe_url(value):
    """Allow http(s), mailto and relative URLs; reject ``javascript:`` etc."""
    if not value:
        return ''
    value = str(value).strip()
    if not value:
        return ''

    # Browsers ignore control characters and whitespace inside a scheme, so
    # ``java\nscript:`` must be rejected as well.
    compact = re.sub(r'[\x00-\x20]+', '', value)
    first_segment = compact.split('/', 1)[0]
    if ':' in first_segment:
        scheme = first_segment.split(':', 1)[0].lower()
        if scheme not in ALLOWED_PROTOCOLS:
            return ''
        return value

    # Relative paths such as ``uploads/file.pdf`` or ``/courses`` are fine.
    return value
