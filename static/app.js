(() => {
  const updateClock = () => {
    const value = new Intl.DateTimeFormat([], { dateStyle: 'medium', timeStyle: 'short' }).format(new Date());
    document.querySelectorAll('#topbar-clock, #sidebar-clock').forEach((element) => { element.textContent = value; });
  };
  updateClock();
  window.setInterval(updateClock, 30000);

  const feed = document.querySelector('#latest-mqtt-feed');
  const liveStatus = document.querySelector('#mqtt-live-status');
  const haSnapshot = document.querySelector('#ha-snapshot');
  const haLiveStatus = document.querySelector('#ha-live-status');
  if (!feed && !haSnapshot) return;

  const relativeTime = (value) => {
    if (!value) return 'unknown';
    const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000));
    if (seconds < 60) return `${seconds} sec ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes} min ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} hr ago`;
    return `${Math.floor(hours / 24)} days ago`;
  };

  const renderHaSnapshot = (entities) => {
    haSnapshot.replaceChildren();
    if (!entities.length) {
      const empty = document.createElement('p');
      empty.className = 'empty-state';
      empty.textContent = 'No Home Assistant states cached yet.';
      haSnapshot.appendChild(empty);
      return;
    }
    entities.forEach((entity) => {
      const row = document.createElement('div');
      row.className = 'ha-snapshot-row';
      const name = document.createElement('span');
      name.className = 'ha-snapshot-name';
      name.title = entity.entity_id;
      name.textContent = entity.name || entity.entity_id;
      const value = document.createElement('strong');
      value.className = 'ha-snapshot-value';
      value.textContent = entity.value == null ? 'unknown' : String(entity.value);
      const updated = document.createElement('time');
      updated.className = 'ha-snapshot-time';
      updated.dateTime = entity.last_updated_at || '';
      updated.title = entity.last_updated_at || 'Unknown update time';
      updated.textContent = relativeTime(entity.last_updated_at);
      row.append(name, value, updated);
      haSnapshot.appendChild(row);
    });
  };

  const refreshHaSnapshot = async () => {
    if (!haSnapshot || document.hidden) return;
    try {
      const response = await fetch('/api/dashboard/random-ha', { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      renderHaSnapshot(data.entities || []);
      haLiveStatus.textContent = 'Live';
      haLiveStatus.className = 'badge success';
    } catch (_error) {
      haLiveStatus.textContent = 'Offline';
      haLiveStatus.className = 'badge warning';
    }
  };

  const renderMqttFeed = (messages) => {
    if (!feed) return;
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
    if (!feed || document.hidden) return;
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

  refreshHaSnapshot();
  refreshMqttFeed();
  window.setInterval(refreshHaSnapshot, 10000);
  window.setInterval(refreshMqttFeed, 2000);
})();