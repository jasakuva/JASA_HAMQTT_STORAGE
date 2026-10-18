from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader

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
    assert "graph-range-button" in content
    assert "Plotly.relayout('graph'" in content
    assert "data-range=\"1h\"" in content
    assert "data-range=\"6h\"" in content
    assert "data-range=\"1d\"" in content
    assert "data-range=\"all\"" in content
    assert ".standalone-shell{grid-template-columns:minmax(0,1fr)}" in styles
    assert ".standalone-graph-panel{flex:1 1 auto;min-height:0;height:calc(100vh - 142px)}" in styles


def test_graph_catalog_filters_zigbee2mqtt_bridge_topics():
    with open("src/hamqtt_store/web.py", encoding="utf-8") as source:
        content = source.read()

    assert 'MQTTTopic.topic.label("topic")' in content
    assert 'if not should_skip_mqtt_parsing(row["topic"])' in content
    assert web.should_skip_mqtt_parsing("zigbee2mqtt/bridge/definitions")
    assert not web.should_skip_mqtt_parsing("zigbee2mqtt/living_room_sensor")


def test_settings_subpage_routes_are_registered():
    app = web.create_app()
    rules = {rule.rule for rule in app.url_map.iter_rules()}

    assert "/settings" in rules
    assert "/settings/<section>" in rules
    assert "/settings/logs" in rules
    assert "/settings/backup-files" in rules
    assert "/settings/backup-files/download/<path:filename>" in rules
    assert "/settings/backup-files/upload" in rules
    assert "/settings/backup-files/recover/<job_id>" in rules


def test_settings_template_contains_requested_sections():
    with open("templates/settings.html", encoding="utf-8") as template:
        content = template.read()

    assert "Authentication" in content
    assert "Data sources" in content
    assert "settings_logs_view" in content
    assert "PostgreSQL backups" in content
    assert "Backup files and recovery" in content


def test_settings_template_compiles():
    environment = Environment(loader=FileSystemLoader("templates"))

    environment.get_template("settings.html")
    environment.get_template("backup_files.html")
    environment.get_template("maintenance.html")