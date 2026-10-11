"""Phase 3-4 (P3): the Streamlit app itself, driven headlessly with streamlit.testing.AppTest."""
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

st_testing = pytest.importorskip("streamlit.testing.v1")


@pytest.fixture
def app(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = st_testing.AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    return at


def _metric(at, label):
    return next(m for m in at.metric if m.label == label).value


def test_first_screen(app):
    assert _metric(app, "Overall score").endswith("/100")
    assert int(_metric(app, "Active risks (72 h)")) >= 1
    assert not app.error


def test_inject_updates_and_reset_restores(app):
    before = (_metric(app, "Overall score"), _metric(app, "Active risks (72 h)"))
    app.button[0].click().run()                      # "Inject anomaly" (default: energy spike)
    assert not app.exception
    assert app.session_state["injections"] == (("energy_kwh", "spike", 2.5, 6),)
    after = (_metric(app, "Overall score"), _metric(app, "Active risks (72 h)"))
    assert after != before
    app.button[0].click().run()                      # same metric again: replaced, not compounded
    assert len(app.session_state["injections"]) == 1
    next(b for b in app.button if b.label.startswith("Reset")).click().run()
    assert app.session_state["injections"] == () and app.session_state["scenario"] is None
    assert (_metric(app, "Overall score"), _metric(app, "Active risks (72 h)")) == before


@pytest.mark.parametrize("sid", ["heatwave", "pipe_leak", "missed_pickup"])
def test_scenario_toggle(app, sid):
    app.button(key=f"sc_{sid}").click().run()
    assert app.session_state["scenario"] == sid and not app.exception
    app.button(key=f"sc_{sid}").click().run()        # toggle off
    assert app.session_state["scenario"] is None


@pytest.mark.parametrize("role", ["admin", "ops", "sustainability"])
def test_roles_render(app, role):
    app.radio(key="role").set_value(role).run()
    assert not app.exception


def test_offline_labels_are_visible(app):
    html = " ".join(m.value for m in app.markdown)
    assert "Template - no API key" in html
