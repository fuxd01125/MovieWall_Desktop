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
    currentSort: "default",
    sortMenuOpen: false,
    filterPanelOpen: false,
    activeFilters: {types: [], yearMin: null, yearMax: null, ratingMin: null, ratingSource: "tmdb", genres: []},
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

  function applyFilters(items) {
    var f = state.activeFilters;
    var hasType = f.types.length > 0;
    var hasYearMin = f.yearMin !== null && f.yearMin !== "";
    var hasYearMax = f.yearMax !== null && f.yearMax !== "";
    var hasRating = f.ratingMin !== null && f.ratingMin !== "" && Number(f.ratingMin) > 0;
    var hasGenres = f.genres.length > 0;
    if (!hasType && !hasYearMin && !hasYearMax && !hasRating && !hasGenres) return items;
    return items.filter(function(item) {
      if (hasType && !f.types.includes(item.type)) return false;
      var y = parseInt(item.year) || 0;
      if (hasYearMin && y < Number(f.yearMin)) return false;
      if (hasYearMax && y > Number(f.yearMax)) return false;
      if (hasRating) {
        var r = f.ratingSource === "douban"
          ? Number(util.douban(item).rating) || 0
          : Number(util.tmdb(item).rating) || 0;
        if (r < Number(f.ratingMin)) return false;
      }
      if (hasGenres) {
        var itemGenres = util.tmdb(item).genres || [];
        if (!f.genres.some(function(g) { return itemGenres.includes(g); })) return false;
      }
      return true;
    });
  }

  function getFilteredSortedItems() {
    return sortItems(applyFilters(getFilteredItems()));
  }

  function getAllGenres() {
    var set = {};
    state.library.items.forEach(function(item) {
      (util.tmdb(item).genres || []).forEach(function(g) { if (g) set[g] = true; });
    });
    return Object.keys(set).sort();
  }

  function hasActiveFilters() {
    var f = state.activeFilters;
    return f.types.length > 0 || f.yearMin || f.yearMax || f.ratingMin || f.genres.length > 0;
  }

  function clearFilters() {
    state.activeFilters = {types: [], yearMin: null, yearMax: null, ratingMin: null, ratingSource: "tmdb", genres: []};
    state.filterPanelOpen = false;
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

  /* ── Sort ── */

  var SORT_MODES = [
    {key: "default",      label: "默认"},
    {key: "recent_add",   label: "最近添加"},
    {key: "recent_watch", label: "最近观看"},
    {key: "rating_desc",  label: "TMDB评分 ↓"},
    {key: "rating_asc",   label: "TMDB评分 ↑"}
  ];

  function initSort() {
    var saved = localStorage.getItem("mw_sort");
    var valid = SORT_MODES.some(function(m) { return m.key === saved; });
    state.currentSort = valid ? saved : "default";
  }

  function setSort(mode) {
    state.currentSort = mode;
    state.sortMenuOpen = false;
    localStorage.setItem("mw_sort", mode);
  }

  function sortItems(items) {
    var mode = state.currentSort;
    if (mode === "default") return items;
    var copy = items.slice();
    if (mode === "recent_add") {
      return copy.sort(function(a, b) { return (b.updated_at || b.created_at || 0) - (a.updated_at || a.created_at || 0); });
    }
    if (mode === "recent_watch") {
      return copy.sort(function(a, b) {
        var ha = state.historyCache[a.id];
        var hb = state.historyCache[b.id];
        var ta = ha ? (ha.played_at || 0) : -1;
        var tb = hb ? (hb.played_at || 0) : -1;
        return tb - ta;
      });
    }
    var desc = mode === "rating_desc";
    return copy.sort(function(a, b) {
      var ra = Number(util.tmdb(a).rating) || 0;
      var rb = Number(util.tmdb(b).rating) || 0;
      var aHas = ra > 0;
      var bHas = rb > 0;
      if (!aHas && !bHas) return 0;
      if (!aHas) return 1;
      if (!bHas) return -1;
      return desc ? rb - ra : ra - rb;
    });
  }

  function getSortLabel(key) {
    for (var i = 0; i < SORT_MODES.length; i++) {
      if (SORT_MODES[i].key === key) return SORT_MODES[i].label;
    }
    return "默认";
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
    initSort();
  }

  /* ── Expose on MW.state ── */

  state.findItem = findItem;
  state.isFavorite = isFavorite;
  state.getUserRating = getUserRating;
  state.getItemHistory = getItemHistory;
  state.getLastHistory = getLastHistory;
  state.getFilteredItems = getFilteredItems;
  state.getFilteredSortedItems = getFilteredSortedItems;
  state.getContinueItems = getContinueItems;
  state.normalizeCategoriesConfig = normalizeCategoriesConfig;
  state.fetchAllData = fetchAllData;
  state.initSort = initSort;
  state.setSort = setSort;
  state.sortItems = sortItems;
  state.getSortLabel = getSortLabel;
  state.SORT_MODES = SORT_MODES;
  state.applyFilters = applyFilters;
  state.getAllGenres = getAllGenres;
  state.hasActiveFilters = hasActiveFilters;
  state.clearFilters = clearFilters;

  MW.state = state;

})();
