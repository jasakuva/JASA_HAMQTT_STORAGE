(() => {
  const updateClock = () => {
    const value = new Intl.DateTimeFormat([], { dateStyle: 'medium', timeStyle: 'short' }).format(new Date());
    document.querySelectorAll('#topbar-clock, #sidebar-clock').forEach((element) => { element.textContent = value; });
  };
  updateClock();
  window.setInterval(updateClock, 30000);

  const feed = document.querySelector('#latest-mqtt-feed');
  const liveStatus = document.querySelector('#mqtt-live-status');
  if (!feed) return;

  const renderMqttFeed = (messages) => {
    feed.replaceChildren();
    if (!messages.length) {
      const empty = document.createElement('p');
      empty.className = 'empty-state';
      empty.textContent = 'No MQTT messages cached yet.';
      feed.appendChild(empty);
      return;
    }
    messages.forEach((message) => {
      const row = document.createElement('div');
      row.className = 'mqtt-feed-row';
      const time = document.createElement('time');
      time.dateTime = message.received_at;
      time.textContent = new Date(message.received_at).toLocaleTimeString();
      const topic = document.createElement('span');
      topic.className = 'mqtt-feed-topic';
      topic.title = message.topic;
      topic.textContent = message.topic;
      const payload = document.createElement('span');
      payload.className = 'mqtt-feed-message';
      payload.title = message.message;
      payload.textContent = message.message;
      row.append(time, topic, payload);
      feed.appendChild(row);
    });
  };

  const refreshMqttFeed = async () => {
    if (document.hidden) return;
    try {
      const response = await fetch('/api/dashboard/latest-mqtt', { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      renderMqttFeed(data.messages || []);
      liveStatus.textContent = 'Live';
      liveStatus.className = 'badge success';
    } catch (_error) {
      liveStatus.textContent = 'Offline';
      liveStatus.className = 'badge warning';
    }
  };

  refreshMqttFeed();
  window.setInterval(refreshMqttFeed, 2000);
})();