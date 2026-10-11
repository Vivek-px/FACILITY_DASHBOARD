"""Declarative working-data state.

The app never keeps a mutated DataFrame in session state. It keeps a small, hashable
*description* of the modifications - (scenario, injections) - and rebuilds the working
frame from the untouched base every run. Consequences:
  * reruns can never compound mutations (same description -> same frame),
  * Reset = clear the description,
  * the description is a perfect cache key for st.cache_data.
"""
from facility.data.injection import inject_anomaly
from facility.data.scenarios import apply_scenario

# one injection = (metric, kind, magnitude, hours)


def add_injection(injections, metric, kind="spike", magnitude=2.5, hours=6):
    """Return a new tuple where `metric` has exactly one injection (replaces any
    previous one for that metric). Different metrics may coexist -> compound demo."""
    kept = tuple(i for i in injections if i[0] != metric)
    return kept + ((metric, kind, float(magnitude), int(hours)),)


def build_working_df(base, scenario=None, injections=()):
    """Rebuild the working frame from base. Returns (df, [InjectionEvent])."""
    df = apply_scenario(base, scenario) if scenario else base.copy()
    events = []
    for metric, kind, magnitude, hours in injections:
        df, ev = inject_anomaly(df, metric, hours=hours, magnitude=magnitude, kind=kind)
        events.append(ev)
    return df, events
