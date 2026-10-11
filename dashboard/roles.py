"""Role-based views: ONE analytics result, three lenses (PRD §6.2 - 'same data, filtered differently').

Architecture:
  * Every Recommendation carries `roles` (from its template) = who is responsible.
  * `split_for_role` puts the current role's actions first (Admin additionally sees every
    HIGH-severity risk - escalation); nothing is hidden - other
    teams' actions sit in a collapsed section, so no role loses situational awareness.
  * ROLE_VIEWS sets the question each role asks and which overview panel answers it.
No role has its own analytics, data or app.
"""
ROLE_VIEWS = {
    "admin": {"question": "Is the facility on track, and which risks need my decision?",
              "panel": "score_breakdown"},
    "ops": {"question": "What must my team do this shift, and when is the next peak?",
            "panel": "next_24h"},
    "sustainability": {"question": "Where are we using more energy, water or waste than our baseline?",
                       "panel": "vs_baseline"},
}


def split_for_role(recs, role):
    """(mine, others). Escalation rule: the Admin also owns every HIGH-severity risk."""
    mine = [r for r in recs if role in r.roles or (role == "admin" and r.severity == "high")]
    ids = {id(r) for r in mine}
    others = [r for r in recs if id(r) not in ids]
    return mine, others
