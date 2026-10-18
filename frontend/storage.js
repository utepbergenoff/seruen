/* Серуен: what a person keeps on this device: places (want to go, visited, favourite, note) and saved walks.
   IndexedDB, schema version 1. Nothing here is sent anywhere; the service worker cache is separate, so an app
   update never deletes it. When the browser refuses storage (private mode, blocked site data) the same API keeps
   data in memory for this visit and reports why, so the page can say so instead of losing notes silently. */
(() => {
  "use strict";
  const DB = "seruen", VERSION = 1;
  const memory = {places: new Map(), walks: new Map()};
  let db = null, problem = null;

  const req = (r) => new Promise((ok, fail) => { r.onsuccess = () => ok(r.result); r.onerror = () => fail(r.error); });
  const tx = (name, mode, fn) => new Promise((ok, fail) => {
    const t = db.transaction(name, mode), out = fn(t.objectStore(name));
    t.oncomplete = () => ok(out && "result" in out ? out.result : out);
    t.onerror = () => fail(t.error); t.onabort = () => fail(t.error);
  });
  const reason = (e) => (e && e.name === "QuotaExceededError" ? "quota" : "blocked");

  function open() {
    return new Promise((ok) => {
      let r;
      try { r = window.indexedDB && window.indexedDB.open(DB, VERSION); } catch (e) { problem = reason(e); ok(null); return; }
      if (!r) { problem = "blocked"; ok(null); return; }
      r.onupgradeneeded = () => {
        const d = r.result;
        if (!d.objectStoreNames.contains("places")) d.createObjectStore("places", {keyPath: "poi_id"});
        if (!d.objectStoreNames.contains("walks")) d.createObjectStore("walks", {keyPath: "id"});
      };
      r.onsuccess = () => ok(r.result);
      r.onerror = () => { problem = reason(r.error); ok(null); };
      r.onblocked = () => { problem = "blocked"; ok(null); };
    });
  }

  // visits marked before this store existed (the old coin feature) become plain visits; the old key stays
  async function migrate() {
    let old = {};
    try {
      if (localStorage.getItem("seruen_store_migrated") === "1") return;
      old = JSON.parse(localStorage.getItem("seruen_visited") || "{}") || {};
    } catch { return; }
    for (const [poi_id, ts] of Object.entries(old)) {
      const cur = await api.getPlace(poi_id);
      await api.putPlace({poi_id, name: cur?.name || "", ...cur, visited_at: cur?.visited_at || (+ts || Date.now())});
    }
    try { localStorage.setItem("seruen_store_migrated", "1"); } catch { /* private mode: migrate again next time */ }
  }

  const api = {
    get problem() { return problem; },
    async init() {
      db = await open();
      await migrate();
      return api;
    },
    async getPlace(id) { return db ? tx("places", "readonly", (s) => s.get(id)) : memory.places.get(id); },
    async allPlaces() { return db ? tx("places", "readonly", (s) => s.getAll()) : [...memory.places.values()]; },
    async putPlace(p) {
      const row = {name: "", want: false, favorite: false, note: "", visited_at: null, ...p, updated_at: Date.now()};
      const empty = !row.want && !row.favorite && !row.note && !row.visited_at;
      if (empty) return api.deletePlace(row.poi_id);  // nothing left to keep
      if (!db) { memory.places.set(row.poi_id, row); return row; }
      try { await tx("places", "readwrite", (s) => s.put(row)); } catch (e) { problem = reason(e); throw e; }
      return row;
    },
    async deletePlace(id) { if (!db) { memory.places.delete(id); return; } await tx("places", "readwrite", (s) => s.delete(id)); },
    async clearPlaces() { if (!db) { memory.places.clear(); return; } await tx("places", "readwrite", (s) => s.clear()); },
    async saveWalk(plan) {
      const row = {...plan, id: plan.id || `w${Date.now()}`};
      if (!db) { memory.walks.set(row.id, row); return row; }
      try { await tx("walks", "readwrite", (s) => s.put(row)); } catch (e) { problem = reason(e); throw e; }
      return row;
    },
    async allWalks() { return db ? tx("walks", "readonly", (s) => s.getAll()) : [...memory.walks.values()]; },
    async getWalk(id) { return db ? tx("walks", "readonly", (s) => s.get(id)) : memory.walks.get(id); },
    async deleteWalk(id) { if (!db) { memory.walks.delete(id); return; } await tx("walks", "readwrite", (s) => s.delete(id)); },
    async clearAll() { await api.clearPlaces(); if (!db) { memory.walks.clear(); return; } await tx("walks", "readwrite", (s) => s.clear()); },
  };
  window.SeruenStore = api;
})();
