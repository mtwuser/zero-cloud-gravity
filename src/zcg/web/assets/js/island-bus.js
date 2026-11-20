// ZeroCloudGravity — Canonical Replay-Capable Pub/Sub Island Event Bus (ES2024)
(() => {
  const subscribers = new Map();
  const lastPayloads = new Map();

  window.IslandBus = {
    emit(topic, payload) {
      lastPayloads.set(topic, payload);
      for (const listener of subscribers.get(topic) || []) {
        listener(payload);
      }
    },

    on(topic, listener, { replay = true } = {}) {
      if (!subscribers.has(topic)) {
        subscribers.set(topic, new Set());
      }
      subscribers.get(topic).add(listener);
      if (replay && lastPayloads.has(topic)) {
        listener(lastPayloads.get(topic));
      }
      return () => subscribers.get(topic)?.delete(listener);
    },

    getLast(topic) {
      return lastPayloads.get(topic);
    },
  };
})();
