"""CSS and HTML card helpers. All dynamic text is HTML-escaped (LLM output included)."""
import html

import streamlit as st

from facility.contracts import ROLE_LABELS

CSS = """<style>
.block-container{padding-top:2.2rem;padding-bottom:2rem;max-width:1400px}
.hero{background:#fff;border:1px solid #D5DFE3;border-left:8px solid var(--c);border-radius:8px;
      padding:14px 18px;margin:4px 0 12px 0}
.hero .kicker{font-size:.78rem;letter-spacing:.06em;text-transform:uppercase;color:#5A6E78}
.hero .text{font-size:1.15rem;font-weight:600;color:#10242E;margin-top:2px}
.pill{display:inline-block;padding:2px 10px;border-radius:12px;color:#fff;font-size:.8rem;font-weight:600;
      background:var(--c)}
.card{background:#fff;border:1px solid #D5DFE3;border-left:6px solid var(--c);border-radius:6px;
      padding:12px 16px;margin:8px 0 2px 0}
.card h4{margin:0 0 4px 0;font-size:1.02rem;color:#10242E}
.card .act{color:#10242E;font-size:.95rem}
.card .as{color:#5A6E78;font-size:.85rem;margin-top:6px}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:.74rem;background:#EEF3F5;
       margin:6px 6px 0 0;color:#10242E}
.badge.ai{background:#E3F2EF;color:#0B5F5E}.badge.tpl{background:#FFF4E0;color:#7A5200}
.muted{color:#5A6E78;font-size:.85rem}
</style>"""

SEV_COLOR = {"high": "#C0392B", "medium": "#B87A00", "low": "#0E7C7B"}


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def hero(kicker, text, color):
    st.markdown(f'<div class="hero" style="--c:{color}"><div class="kicker">{html.escape(kicker)}</div>'
                f'<div class="text">{html.escape(text)}</div></div>', unsafe_allow_html=True)


def pill(text, color):
    return f'<span class="pill" style="--c:{color}">{html.escape(text)}</span>'


def card(rec):
    e = html.escape
    if rec.source == "llm":
        src = '<span class="badge ai">AI-written (Claude)</span>'
    else:
        reason = f" - {rec.fallback_reason}" if rec.fallback_reason else ""
        src = f'<span class="badge tpl">Template{e(reason)}</span>'
    roles = "".join(f'<span class="badge">{e(ROLE_LABELS.get(r, r))}</span>' for r in rec.roles)
    st.markdown(
        f'<div class="card" style="--c:{SEV_COLOR.get(rec.severity, "#0E7C7B")}">'
        f'<h4>{e(rec.title)}</h4><div class="act">{e(rec.action)}</div>'
        f'<div class="as"><b>Assumption:</b> {e(rec.assumption)}</div>'
        f'<span class="badge">Priority {rec.priority} - {e(rec.severity)}</span>{roles}{src}</div>',
        unsafe_allow_html=True)
