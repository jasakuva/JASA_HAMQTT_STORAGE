from html.parser import HTMLParser
from urllib.parse import urlencode
from urllib.request import urlopen


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []

    def handle_data(self, data):
        self.text.append(data)


def fetch(path, params=None):
    url = "http://localhost:8000" + path
    if params:
        url += "?" + urlencode(params)
    with urlopen(url, timeout=10) as response:
        body = response.read().decode("utf-8")
        assert response.status == 200, (path, response.status)
        return body


ha_search = fetch("/ha", {"q": "temperature"})
assert "Search entity ID" in ha_search
assert "View state/history" in ha_search

mqtt_search = fetch("/mqtt", {"q": "smoke"})
assert "Search MQTT topics" in mqtt_search
assert "View history" in mqtt_search

objects_search = fetch("/objects", {"q": "temperature"})
assert "Search identifier, name, nickname" in objects_search

ha_detail = fetch("/ha/entities/34")
for text in ("Current state", "Attributes", "Last changed", "Last updated", "State history"):
    assert text in ha_detail, text

mqtt_detail = fetch("/mqtt/topics/1")
for text in ("Current parsed fields", "Parsed observation history", "Raw message history"):
    assert text in mqtt_detail, text

print("UI search/detail/history verification passed")
