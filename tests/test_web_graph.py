from types import SimpleNamespace

from hamqtt_store import web


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def scalar(self, statement):
        return SimpleNamespace(id=7, session_version=1)


def test_plot_link_redirects_to_standalone_graph(monkeypatch):
    monkeypatch.setattr(web, "SessionLocal", FakeSession)
    app = web.create_app()
    app.config.update(TESTING=True)

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 7
            session["session_version"] = 1

        response = client.get("/plot/42")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/graph?object_id=42&standalone=1")


def test_standalone_graph_layout_contract_is_present():
    with open("templates/graph.html", encoding="utf-8") as template:
        content = template.read()
    with open("static/layout-fixes.css", encoding="utf-8") as stylesheet:
        styles = stylesheet.read()

    assert "standalone-graph-page" in content
    assert "standalone-graph-panel" in content
    assert "Plotly.Plots.resize('graph')" in content
    assert ".standalone-graph-panel{flex:1 1 auto;min-height:0;height:calc(100vh - 142px)}" in styles