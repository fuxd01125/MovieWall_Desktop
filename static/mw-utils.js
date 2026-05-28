/* ============================================================
   MovieWall — Utility Functions
   Pure helpers: HTML escaping, metadata access, artwork URLs, toast
   ============================================================ */

window.MW = window.MW || {};

(function() {
  "use strict";

  function escapeHtml(s) {
    return String(s || "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");
  }

  function escapeJs(s) {
    return String(s || "").replaceAll("\\","\\\\").replaceAll("'","\\'").replaceAll("\n","\\n").replaceAll("\r","\\r");
  }

  function titleOf(item) { return item?.display_title || item?.title || item?.filename || "未命名"; }

  function tmdb(item) { return item?.metadata?.tmdb || {}; }
  function douban(item) { return item?.metadata?.douban || {}; }
  function seasonTmdb(season) { return season?.metadata?.tmdb || season?.tmdb || {}; }
  function seasonDouban(season) { return season?.metadata?.douban || season?.douban || {}; }
  function creditsCast(item) { return item?.metadata?.credits?.cast || []; }

  function artworkUrl(item, kind) {
    kind = kind || "poster";
    if (!item) return "";
    if (item.type === "show") {
      const t = tmdb(item);
      if (kind === "poster" && t.poster_url) return t.poster_url;
    }
    if (item[kind]) {
      if (String(item[kind]).startsWith("http")) return item[kind];
      return "/api/artwork/" + item.id + "/" + kind;
    }
    if (item.type === "episode" && kind === "thumb") return "";
    const t = tmdb(item);
    if (kind === "poster" && t.poster_url) return t.poster_url;
    if ((kind === "thumb" || kind === "backdrop") && t.backdrop_url) return t.backdrop_url;
    if ((kind === "thumb" || kind === "backdrop") && t.poster_url) return t.poster_url;
    return "";
  }

  function backdropUrl(item) {
    return tmdb(item).backdrop_url || artworkUrl(item, "thumb") || artworkUrl(item, "poster");
  }

  function showToast(msg, duration) {
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = msg;
    document.body.appendChild(el);
    requestAnimationFrame(function() { el.classList.add("show"); });
    setTimeout(function() {
      el.classList.remove("show");
      setTimeout(function() { el.remove(); }, 300);
    }, duration || 2500);
  }

  function highlightText(text, query) {
    if (!query) return escapeHtml(text);
    var escaped = escapeHtml(text);
    var q = escapeHtml(query).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return escaped.replace(new RegExp('(' + q + ')', 'gi'), '<mark>$1</mark>');
  }

  function renderDualRating(item) {
    var t = tmdb(item);
    var d = douban(item);
    var tRating = t.rating || "";
    var dRating = d.rating || "";
    var dCount = d.rating_count || "";
    var html = '';
    if (dRating) {
      html += '<span class="rating-badge douban">豆瓣 ' + Number(dRating).toFixed(1) + '</span>';
    }
    if (tRating) {
      html += '<span class="rating-badge tmdb">TMDB ' + Number(tRating).toFixed(1) + '</span>';
    }
    if (dCount) {
      html += '<span class="rating-badge douban-count">' + Number(dCount).toLocaleString() + ' 评</span>';
    }
    return html;
  }

  /* Expose on MW.util */
  MW.util = {
    escapeHtml: escapeHtml,
    escapeJs: escapeJs,
    titleOf: titleOf,
    tmdb: tmdb,
    douban: douban,
    seasonTmdb: seasonTmdb,
    seasonDouban: seasonDouban,
    creditsCast: creditsCast,
    artworkUrl: artworkUrl,
    backdropUrl: backdropUrl,
    showToast: showToast,
    highlightText: highlightText,
    renderDualRating: renderDualRating
  };

  /* Expose on window for inline onclick handlers */
  window.showToast = showToast;

})();
