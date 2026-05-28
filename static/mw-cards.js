/* ============================================================
   MovieWall — Card Rendering
   Home cards, continue cards, hero banner, row sections
   Depends on: mw-utils.js, mw-state.js, mw-detail.js
   ============================================================ */

window.MW = window.MW || {};

(function() {
  "use strict";

  var util = MW.util;
  var state = MW.state;

  function pickHeroItem(items, continueItems, hasQuery) {
    if (hasQuery) return null;
    var ci = continueItems[0];
    if (ci) return ci.item;
    var pick = items[Math.floor(Math.random() * Math.min(3, items.length))];
    return pick || items[0] || null;
  }

  function renderHero(item) {
    if (!item) return '';
    var t = util.tmdb(item);
    var d = util.douban(item);
    var backdropRaw = t.backdrop_url || util.artworkUrl(item, "thumb") || t.poster_url || util.artworkUrl(item, "poster");
    var posterRaw = util.artworkUrl(item, "poster") || t.poster_url;
    var heroRating = d.rating || t.rating || "";
    var genres = (t.genres || []).slice(0, 3);
    var isShow = item.type === "show";
    var firstEp = isShow ? MW.detail.findFirstEpisode(item) : null;
    var hist = state.getItemHistory(item);
    var playAction = isShow && firstEp
      ? "playMedia('" + util.escapeJs(firstEp.ep.path) + "'," + MW.detail.episodeEntry(item, firstEp.season, firstEp.ep, firstEp.season.title + " · " + firstEp.ep.title) + ")"
      : hist ? "playItemHistory('" + item.id + "')" : "openDetail('" + item.id + "')";
    var playLabel = isShow && hist ? "▶ 继续播放" : (hist ? "▶ 继续播放" : "▶ 立即观看");
    var typeLabel = isShow ? ((item.season_count || 0) + ' 季 · ' + (item.episode_count || 0) + ' 集') : '电影';

    var pageBg = '';
    if (backdropRaw) {
      pageBg += '<div class="page-backdrop">'
        + '<div class="page-backdrop-img" style="background-image:url(\'' + backdropRaw + '\')"></div>'
        + '<div class="page-backdrop-overlay"></div>'
        + '</div>';
    }

    return pageBg
      + '<div class="hero' + (hist ? ' is-continue' : '') + '">'
      + '<div class="hero-content">'
      + '<div class="hero-badge">' + (hist ? '继续观看' : '今日推荐') + '</div>'
      + '<h1 class="hero-title">' + util.escapeHtml(util.titleOf(item)) + '</h1>'
      + '<div class="hero-meta">'
      + (heroRating ? '<span class="rating-badge lg' + (d.rating ? ' douban' : '') + '">★ ' + Number(heroRating).toFixed(1) + '</span>' : '')
      + (item.year ? '<span class="year">' + util.escapeHtml(item.year) + '</span>' : '')
      + '<span class="year">' + util.escapeHtml(typeLabel) + '</span>'
      + (genres.length ? genres.map(function(g) { return '<span class="genre-tag">' + util.escapeHtml(g) + '</span>'; }).join('') : '')
      + '</div>'
      + '<div class="hero-overview">' + util.escapeHtml(t.overview || d.synopsis || "") + '</div>'
      + '<div class="hero-actions">'
      + '<button class="cta-btn" onclick="event.stopPropagation();' + playAction + '">' + playLabel + '</button>'
      + '<button class="cta-btn secondary' + (state.isFavorite(item.id) ? ' favorited' : '') + '" onclick="event.stopPropagation();toggleFavorite(\'' + item.id + '\')">' + (state.isFavorite(item.id) ? '♥ 已收藏' : '♡ 收藏') + '</button>'
      + '<button class="cta-btn secondary" onclick="event.stopPropagation();openDetail(\'' + item.id + '\')">详情</button>'
      + '</div></div>'
      + (posterRaw ? '<div class="hero-poster"><img src="' + posterRaw + '" loading="lazy" alt=""></div>' : '')
      + '</div>';
  }

  function renderRowSection(title, items, renderFn, moreKey) {
    if (!items || !items.length) return '';
    var moreLink = moreKey ? ' onclick="setTab(\'' + moreKey + '\')"' : '';
    return '<section class="row-section">'
      + '<div class="row-header"><h2>' + util.escapeHtml(title) + '</h2>'
      + (moreLink ? '<span class="row-more"' + moreLink + '>查看全部 →</span>' : '')
      + '</div>'
      + '<div class="row-shell"><div class="row-scroll">'
      + items.map(renderFn).join('')
      + '</div></div></section>';
  }

  function primaryPlayAction(item) {
    var hist = state.getItemHistory(item);
    if (hist) return "playItemHistory('" + item.id + "')";
    if (item.type === "movie" && item.path) {
      var entry = "{media_id:'" + item.id + "',type:'movie',path:'" + util.escapeJs(item.path) + "',title:'" + util.escapeJs(util.titleOf(item)) + "',show_title:'" + util.escapeJs(util.titleOf(item)) + "',label:'电影',short_label:'电影'}";
      return "playMedia('" + util.escapeJs(item.path) + "'," + entry + ")";
    }
    if (item.type === "show") {
      var firstEp = MW.detail.findFirstEpisode(item);
      if (firstEp) {
        return "playMedia('" + util.escapeJs(firstEp.ep.path) + "'," + MW.detail.episodeEntry(item, firstEp.season, firstEp.ep, firstEp.season.title + " · " + firstEp.ep.title) + ")";
      }
    }
    return "openDetail('" + item.id + "')";
  }

  function renderCardOverlay(item) {
    return '<div class="card-overlay">'
      + '<div class="poster-actions">'
      + '<button class="poster-play" onclick="event.stopPropagation();' + primaryPlayAction(item) + '" title="播放">▶</button>'
      + '</div>'
      + '</div>';
  }

  function renderHomeCard(item) {
    var q = document.querySelector("#search").value.trim();
    var fav = state.isFavorite(item.id);
    var t = util.tmdb(item);
    var d = util.douban(item);
    var score = d.rating || t.rating || "";
    var epCount = item.type === "show" ? (item.episode_count || 0) : 0;
    var showCount = item.type === "show" && epCount > 0;
    var badges = (score ? '<div class="card-badge-score">★ ' + Number(score).toFixed(1) + '</div>' : '')
      + (showCount ? '<div class="card-badge-episodes">' + epCount + ' 集</div>' : '')
      + (item.year ? '<div class="card-badge-year">' + util.escapeHtml(item.year) + '</div>' : '');
    return '<article class="card' + (fav ? ' is-fav' : '') + '" onclick="openDetail(\'' + item.id + '\')">'
      + '<div class="card-poster">'
      + (fav ? '<div class="fav-badge">♥</div>' : '')
      + badges
      + (util.artworkUrl(item, "poster")
        ? '<img src="' + util.artworkUrl(item, "poster") + '" loading="lazy" onerror="this.parentElement.innerHTML=\'<div class=\\\'placeholder\\\'>' + util.escapeHtml(util.titleOf(item)) + '</div>\'">'
        : '<div class="placeholder">' + util.escapeHtml(util.titleOf(item)) + '</div>')
      + renderCardOverlay(item)
      + '</div>'
      + '<div class="card-body"><h4 class="card-title">' + util.highlightText(util.titleOf(item), q) + '</h4></div>'
      + '</article>';
  }

  function renderContinueCard(entry) {
    var item = entry.item;
    var hist = entry.hist;
    var title = hist.show_title || hist.title || util.titleOf(item);
    var label = hist.short_label || hist.label || "";
    var isShow = item.type === "show";
    var epContext = hist.season_number ? 'S' + String(hist.season_number).padStart(2,'0') + 'E' + String(hist.episode_number || 0).padStart(2,'0') : label;
    var progressPct = 0;
    if (isShow) {
      var totalEps = item.episode_count || 0;
      var watchedEps = (item.seasons || []).reduce(function(sum, s) {
        return sum + (s.episodes || []).filter(function(ep) { return state.historyCache[ep.id]; }).length;
      }, 0);
      progressPct = totalEps ? Math.round(watchedEps / totalEps * 100) : 0;
    }
    var histEntry = "{media_id:'" + item.id + "',type:'" + item.type + "',path:'" + util.escapeJs(hist.path) + "',title:'" + util.escapeJs(title) + "',show_title:'" + util.escapeJs(hist.show_title || title) + "',label:'" + util.escapeJs(epContext) + "',short_label:'" + util.escapeJs(epContext) + "'}";
    var t = util.tmdb(item);
    var d = util.douban(item);
    var score = d.rating || t.rating || "";
    return '<article class="card continue-card" onclick="playMedia(\'' + util.escapeJs(hist.path) + '\',' + histEntry + ')">'
      + '<div class="card-poster">'
      + (score ? '<div class="card-badge-score">★ ' + Number(score).toFixed(1) + '</div>' : '')
      + (util.artworkUrl(item, "poster")
        ? '<img src="' + util.artworkUrl(item, "poster") + '" loading="lazy" onerror="this.parentElement.innerHTML=\'<div class=\\\'placeholder\\\'>' + util.escapeHtml(title) + '</div>\'">'
        : '<div class="placeholder">' + util.escapeHtml(title) + '</div>')
      + '<div class="card-overlay">'
      + '<div class="poster-actions"><button class="poster-play" onclick="event.stopPropagation();playMedia(\'' + util.escapeJs(hist.path) + '\',' + histEntry + ')" title="继续播放">▶</button></div>'
      + '</div>'
      + (progressPct > 0 ? '<div class="card-progress"><div class="card-progress-bar" style="width:' + progressPct + '%"></div></div>' : '')
      + '</div>'
      + '<div class="card-body">'
      + '<div class="continue-kicker">▶ ' + util.escapeHtml(isShow ? epContext : '继续观看') + '</div>'
      + '<h4 class="card-title">' + util.escapeHtml(title) + '</h4></div>'
      + '</article>';
  }

  function showSkeleton() {
    var card = '<div class="skeleton-card"><div class="skeleton-poster skeleton"></div><div class="skeleton-title skeleton"></div></div>';
    document.querySelector("#app").innerHTML = '<section class="section loading-section"><div class="grid">' + card.repeat(12) + '</div></section>';
  }

  /* Expose on MW.cards */
  MW.cards = {
    pickHeroItem: pickHeroItem,
    renderHero: renderHero,
    renderRowSection: renderRowSection,
    primaryPlayAction: primaryPlayAction,
    renderCardOverlay: renderCardOverlay,
    renderHomeCard: renderHomeCard,
    renderContinueCard: renderContinueCard,
    showSkeleton: showSkeleton
  };

})();
