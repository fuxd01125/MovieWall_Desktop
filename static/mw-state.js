/* ============================================================
   MovieWall — State Management
   Shared mutable state, cache accessors, data fetching
   ============================================================ */

window.MW = window.MW || {};

(function() {
  "use strict";

  var util = MW.util;

  /* ── Shared mutable state ── */

  var state = {
    library: {items: [], stats: {}},
    currentView: {type: "home"},
    navStack: [],
    players: [],
    categoriesConfig: {},
    expandedSeason: null,
    moreMenuOpen: null,
    seasonMoreOpen: null,
    ratingsCache: {},
    historyCache: {},
    favoritesCache: [],
    activeTab: "all",
    historyPollInterval: null
  };

  /* ── State accessors ── */

  function findItem(id) {
    return state.library.items.find(function(i) { return i.id === id; });
  }

  function isFavorite(id) {
    return state.favoritesCache.includes(id);
  }

  function getUserRating(item) {
    return item ? state.ratingsCache[item.id] || null : null;
  }

  function getItemHistory(item) {
    return item ? state.historyCache[item.id] : null;
  }

  function getLastHistory() {
    return state.historyCache.__last || null;
  }

  function getFilteredItems() {
    var q = document.querySelector("#search").value.trim().toLowerCase();
    return state.library.items.filter(function(item) {
      if (state.activeTab === "favorites") {
        return state.favoritesCache.includes(item.id);
      }
      if (state.activeTab.startsWith("cat:")) {
        var catKey = state.activeTab.slice(4);
        if (item.category_key !== catKey) return false;
      }
      if (!q) return true;
      var bag = (util.titleOf(item) + " " + (item.title || "") + " " + (item.year || "") + " " + (item.category_name || "")).toLowerCase();
      if (item.type === "movie") bag += " " + (item.filename || "") + " " + (item.folder || "");
      if (item.type === "show") {
        for (var si = 0; si < (item.seasons || []).length; si++) {
          var s = item.seasons[si];
          for (var ei = 0; ei < (s.episodes || []).length; ei++) {
            var ep = s.episodes[ei];
            bag += " " + (s.title || "") + " " + (ep.title || "") + " " + (ep.filename || "");
          }
        }
      }
      return bag.includes(q);
    });
  }

  function getContinueItems() {
    var items = [];
    for (var mediaId of Object.keys(state.historyCache)) {
      if (mediaId === "__last") continue;
      var hist = state.historyCache[mediaId];
      var item = findItem(mediaId);
      if (item) items.push({item: item, hist: hist});
    }
    var q = document.querySelector("#search").value.trim().toLowerCase();
    return items.filter(function(entry) {
      var item = entry.item;
      if (state.activeTab.startsWith("cat:")) {
        var catKey = state.activeTab.slice(4);
        if (item.category_key !== catKey) return false;
      }
      if (!q) return true;
      var bag = (util.titleOf(item) + " " + (item.title || "") + " " + (item.year || "")).toLowerCase();
      return bag.includes(q);
    }).sort(function(a, b) {
      return (b.hist.played_at || 0) - (a.hist.played_at || 0);
    });
  }

  function normalizeCategoriesConfig(raw) {
    if (!raw) return {};
    var out = {};
    for (var key of Object.keys(raw)) {
      var v = raw[key];
      if (typeof v === "string") out[key] = {name: v};
      else if (v && typeof v === "object") out[key] = {name: v.name || key};
      else out[key] = {name: key};
    }
    return out;
  }

  /* ── Pure data fetching (does NOT trigger rendering) ── */

  async function fetchAllData() {
    var results = await Promise.all([
      fetch("/api/library").then(function(r) { return r.json(); }),
      fetch("/api/ratings").then(function(r) { return r.json(); }),
      fetch("/api/history").then(function(r) { return r.json(); }),
      fetch("/api/favorites").then(function(r) { return r.json(); }),
      fetch("/api/players").then(function(r) { return r.json(); }),
      fetch("/api/config").then(function(r) { return r.json(); })
    ]);

    var lib = results[0];
    state.library = lib || {items: [], stats: {}};
    state.ratingsCache = results[1] || {};
    state.historyCache = results[2] || {};
    state.favoritesCache = results[3] || [];
    state.players = results[4] || [];
    state.categoriesConfig = normalizeCategoriesConfig(results[5]?.categories);
  }

  /* ── Expose on MW.state ── */

  state.findItem = findItem;
  state.isFavorite = isFavorite;
  state.getUserRating = getUserRating;
  state.getItemHistory = getItemHistory;
  state.getLastHistory = getLastHistory;
  state.getFilteredItems = getFilteredItems;
  state.getContinueItems = getContinueItems;
  state.normalizeCategoriesConfig = normalizeCategoriesConfig;
  state.fetchAllData = fetchAllData;

  MW.state = state;

})();
