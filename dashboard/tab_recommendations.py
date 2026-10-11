import streamlit as st

from dashboard.insights import why
from dashboard.roles import split_for_role
from dashboard.style import card
from facility.contracts import ROLE_LABELS


def _cards(v, recs):
    events = {e.risk_id: e for e in v.result.risk_events}
    for r in recs:
        card(r)
        e = events.get(r.risk_id)
        if e is not None:
            with st.expander("Why this appeared"):
                st.write(why(e, v.result.params))
                st.json({k: (str(x) if hasattr(x, "strftime") else x) for k, x in e.evidence.items()
                         if x is not None}, expanded=False)


def render(v):
    recs = v.recs
    if not recs:
        st.success("No active risks in the last 72 hours. Nothing to action.")
        return
    mine, others = split_for_role(recs, v.role)
    st.markdown(f"**{len(mine)} action(s) for {ROLE_LABELS[v.role]}**, most urgent first")
    _cards(v, mine)
    if others:
        with st.expander(f"Other teams' actions ({len(others)})"):
            _cards(v, others)
