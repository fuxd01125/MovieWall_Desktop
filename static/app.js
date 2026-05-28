/* ============================================================
   MovieWall — Main Application
   Routing, rendering, and user interaction
   Depends on: mw-utils.js (MW.util), mw-api.js (MW.api), mw-state.js (MW.state)
   ============================================================ */

/* ===== MW Module Aliases ===== */
const { escapeHtml, escapeJs, titleOf, tmdb, douban, seasonTmdb, seasonDouban, creditsCast, artworkUrl, backdropUrl, showToast, highlightText, renderDualRating } = MW.util;
const { apiPutRating, apiDeleteRating, apiPutHistory, apiToggleFavorite, openFolder, recordPlay } = MW.api;
const { findItem, isFavorite, getUserRating, getItemHistory, getLastHistory, getFilteredItems, getContinueItems, normalizeCategoriesConfig, fetchAllData } = MW.state;

/* State lives in MW.state — always access via MW.state.xxx for reads AND writes */

const app = document.querySelector("#app");
const search = document.querySelector("#search");
const catTabs = document.querySelector("#catTabs");
const scanBtn = document.querySelector("#scanBtn");
const breadcrumb = document.querySelector("#breadcrumb");

/* ===== Real-time History Sync (polls backend during playback) ===== */

function _normalizeTime(t) {
  // Backend stores played_at as Unix timestamp (seconds as float),
  // frontend recordPlay() stores it as ISO string.
  // Normalise both to milliseconds for comparison.
  if (t == null) return 0;
  if (typeof t === 'number') return t * 1000;
  if (typeof t === 'string' && /^\d+(\.\d+)?$/.test(t)) {
    return parseFloat(t) * 1000;
  }
  const ms = new Date(t).getTime();
  return Number.isFinite(ms) ? ms : 0;
}

async function _pollHistory() {
  try {
    const res = await fetch("/api/history");
    const fresh = await res.json();
    let changed = false;
    for (const mediaId of Object.keys(fresh)) {
      const entry = fresh[mediaId];
      const old = MW.state.historyCache[mediaId];
      const oldTime = old ? _normalizeTime(old.played_at) : 0;
      const newTime = _normalizeTime(entry.played_at);
      if (!old || old.episode_id !== entry.episode_id || newTime > oldTime) {
        MW.state.historyCache[mediaId] = entry;
        changed = true;
      }
    }
    // Recompute __last as the entry with the largest played_at
    let latest = null;
    let latestTime = 0;
    for (const mediaId of Object.keys(MW.state.historyCache)) {
      if (mediaId === '__last') continue;
      const e = MW.state.historyCache[mediaId];
      const t = _normalizeTime(e.played_at);
      if (t > latestTime) { latestTime = t; latest = e; }
    }
    if (latest) MW.state.historyCache.__last = latest;
    if (changed) renderRoute(MW.state.currentView);
  } catch (e) { /* ignore poll errors */ }
}

/* ===== Cast Section ===== */

function renderCastSection(cast) {
  if (!cast || !cast.length) return '';
  return '<section class="section cast-section">'
    + '<div class="section-header"><h2>演员</h2><small>' + cast.length + ' 人</small></div>'
    + '<div class="cast-scroll">'
    + cast.map(c => {
      const p = c.person || {};
      const img = p.profile_url
        ? '<img src="' + p.profile_url + '" loading="lazy" onerror="this.parentElement.innerHTML=\'<div class=\\\'cast-avatar-placeholder\\\'>' + escapeHtml((p.name || '?')[0]) + '</div>\'">'
        : '<div class="cast-avatar-placeholder">' + escapeHtml((p.name || '?')[0]) + '</div>';
      return '<article class="cast-card" onclick="openPerson(\'' + escapeJs(p.id || '') + '\')">'
        + '<div class="cast-avatar">' + img + '</div>'
        + '<div class="cast-info">'
        + '<div class="cast-name">' + escapeHtml(p.name || '') + '</div>'
        + '<div class="cast-role">' + escapeHtml(c.character || c.job || '') + '</div>'
        + '</div></article>';
    }).join('')
    + '</div></section>';
}

async function openPerson(personId) {
  if (!personId) return;
  showSkeleton();
  const res = await fetch("/api/person/" + encodeURIComponent(personId));
  if (!res.ok) { showToast("演员信息未能加载", 3000); goHome(); return; }
  const data = await res.json();
  navigateTo({type:"person", data});
}

function renderPersonDetail(data) {
  MW.state.currentView = {type:"person", data};
  renderCategoryTabs();
  renderBreadcrumb();

  const img = data.profile_url
    ? '<img src="' + data.profile_url + '" loading="lazy">'
    : '<div class="placeholder">' + escapeHtml((data.name || '?')[0]) + '</div>';
  const aka = data.also_known_as && data.also_known_as.length
    ? '<div class="person-aka">又名: ' + data.also_known_as.map(n => escapeHtml(n)).join(' / ') + '</div>' : '';

  // Hero section — back button + avatar + info
  let hero = '<div class="person-hero">'
    + '<button class="back-hero-btn" onclick="event.stopPropagation();goBackSmart()" title="返回" aria-label="返回">'
    + '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>'
    + '</button>'
    + '<div class="person-poster">' + img + '</div>'
    + '<div class="person-info">'
    + '<h1>' + escapeHtml(data.name || '') + '</h1>'
    + (data.original_name && data.original_name !== data.name ? '<div class="person-original-name">' + escapeHtml(data.original_name) + '</div>' : '')
    + (data.known_for_department ? '<div class="person-dept">' + escapeHtml(data.known_for_department) + '</div>' : '')
    + (data.birthday ? '<div class="person-meta"><span class="meta-label">出生</span> ' + escapeHtml(data.birthday) + (data.deathday ? ' — ' + escapeHtml(data.deathday) : '') + '</div>' : '')
    + (data.place_of_birth ? '<div class="person-meta"><span class="meta-label">出生地</span> ' + escapeHtml(data.place_of_birth) + '</div>' : '')
    + aka
    + (data.biography ? '<div class="person-bio">' + escapeHtml(data.biography) + '</div>' : '')
    + '</div></div>';

  // Works section
  const works = data.works || [];
  let worksHtml = '';
  if (works.length) {
    worksHtml = '<section class="section"><div class="section-header"><h2>本地作品</h2><small>' + works.length + ' 部</small></div>'
      + '<div class="grid">'
      + works.map(w => {
        const item = findItem(w.media_id);
        const poster = item ? artworkUrl(item, "poster") : '';
        const title = w.display_title || w.media_title || '';
        const role = w.character ? '饰 ' + w.character : (w.job || w.department || '');
        return '<article class="card" onclick="openDetail(\'' + escapeJs(w.media_id) + '\')">'
          + '<div class="card-poster">'
          + (poster
            ? '<img src="' + poster + '" loading="lazy" onerror="this.parentElement.innerHTML=\'<div class=\\\'placeholder\\\'>' + escapeHtml(title) + '</div>\'">'
            : '<div class="placeholder">' + escapeHtml(title) + '</div>')
          + '</div>'
          + '<div class="card-body">'
          + '<h4 class="card-title">' + escapeHtml(title) + '</h4>'
          + (role ? '<div class="person-role">' + escapeHtml(role) + '</div>' : '')
          + '</div></article>';
      }).join('')
      + '</div></section>';
  }

  app.innerHTML = '<div class="person-page">' + hero + worksHtml + '</div>';
}

function startHistoryPolling() {
  if (MW.state.historyPollInterval) return;
  MW.state.historyPollInterval = setInterval(_pollHistory, 3000);
}

function stopHistoryPolling() {
  if (MW.state.historyPollInterval) {
    clearInterval(MW.state.historyPollInterval);
    MW.state.historyPollInterval = null;
  }
}

function setUserRating(itemId, score) {
  MW.state.ratingsCache[itemId] = {score: Number(score), rated_at: new Date().toISOString()};
  renderRoute(MW.state.currentView);
  apiPutRating(itemId, score);
  showToast("评分已保存 " + Number(score).toFixed(1) + " / 10");
}

function clearUserRating(itemId) {
  delete MW.state.ratingsCache[itemId];
  renderRoute(MW.state.currentView);
  apiDeleteRating(itemId);
  showToast("评分已清除");
}

/* ===== Category Tabs ===== */

function renderCategoryTabs() {
  const catStats = MW.state.library.stats?.categories || [];
  // Only "全部" + dynamic categories from library data — no media_type tabs
  const tabs = [
    {key:"all", label:"全部"},
    ...catStats.map(c => ({key:"cat:" + c.key, label: c.name})),
    {key:"favorites", label:"收藏"}
  ];
  catTabs.innerHTML = tabs.map(t =>
    '<button class="cat-tab' + (MW.state.activeTab === t.key ? ' active' : '') + '" onclick="setTab(\'' + t.key + '\')">' + t.label + '</button>'
  ).join("");
}

function setTab(key) {
  MW.state.moreMenuOpen = null;
  MW.state.seasonMoreOpen = null;
  MW.state.activeTab = key;
  MW.state.navStack = [];
  renderHome();
}

/* ===== Star Rating (user input) ===== */

function starRatingWidget(item) {
  const r = getUserRating(item);
  const current = r ? Number(r.score) : 0;
  const fullStars = Math.floor(current / 2);
  const halfStar = (current % 2) >= 1 ? 1 : 0;
  let stars = "";
  for (let i = 1; i <= 5; i++) {
    const val = i * 2;
    let cls = "star star-empty";
    if (i <= fullStars) cls = "star star-full";
    else if (i === fullStars + 1 && halfStar) cls = "star star-half";
    stars += '<span class="' + cls + '" onclick="setUserRating(\'' + item.id + '\',' + val + ')">'
      + (i <= fullStars || (i === fullStars + 1 && halfStar) ? '★' : '☆')
      + '</span>';
  }
  const label = current
    ? '<span class="star-score">' + current.toFixed(1) + '</span>'
    : '<span class="star-hint">我来评分</span>';
  return '<div class="star-rating">'
    + '<span class="star-label">我的评分</span>'
    + '<div class="star-row">' + stars + '</div>'
    + label
    + (current ? '<button class="star-clear" onclick="clearUserRating(\'' + item.id + '\')" title="清除评分">✕</button>' : '')
    + '</div>';
}

/* ===== Breadcrumb ===== */

function renderBreadcrumb() {
  let html = '<span class="bc-item" onclick="goHome()">首页</span>';
  if (MW.state.currentView.type === "detail" || MW.state.currentView.type === "season") {
    const item = findItem(MW.state.currentView.type === "detail" ? MW.state.currentView.id : MW.state.currentView.showId);
    if (item) {
      html += '<span class="bc-sep">/</span><span class="bc-item" onclick="goHome()">' + escapeHtml(item.category_name) + '</span>';
      html += '<span class="bc-sep">/</span><span class="bc-item bc-current">' + escapeHtml(titleOf(item)) + '</span>';
    }
  }
  if (MW.state.currentView.type === "season") {
    const show = findItem(MW.state.currentView.showId);
    const season = (show?.seasons || []).find(s => Number(s.season_number) === Number(MW.state.currentView.seasonNumber));
    if (season) {
      html += '<span class="bc-sep">/</span><span class="bc-item bc-current">' + escapeHtml(season.title) + '</span>';
    }
  }
  breadcrumb.innerHTML = html;
}

/* ===== Routing ===== */

function toggleFavorite(itemId) {
  const wasFav = isFavorite(itemId);
  if (wasFav) {
    MW.state.favoritesCache = MW.state.favoritesCache.filter(id => id !== itemId);
  } else {
    MW.state.favoritesCache.push(itemId);
  }
  renderRoute(MW.state.currentView);
  apiToggleFavorite(itemId);
  showToast(wasFav ? '已取消收藏' : '已收藏');
}

function renderRoute(view) {
  if (!view || view.type === "home") { MW.state.moreMenuOpen = null; return renderHome(); }
  if (view.type === "detail") {
    const item = findItem(view.id);
    if (!item) return renderHome();
    return item.type === "movie" ? renderMovieDetail(item) : renderShowDetail(item);
  }
  if (view.type === "season") {
    const show = findItem(view.showId);
    const season = (show?.seasons || []).find(s => Number(s.season_number) === Number(view.seasonNumber));
    if (!show || !season) return renderHome();
    return renderSeasonDetail(show, season);
  }
  if (view.type === "person") {
    return renderPersonDetail(view.data);
  }
}

function navigateTo(view) {
  MW.state.moreMenuOpen = null;
  MW.state.seasonMoreOpen = null;
  MW.state.navStack.push({...MW.state.currentView});
  MW.state.expandedSeason = null;
  renderRoute(view);
  window.scrollTo({top:0, behavior:"smooth"});
}

function goBackSmart() {
  MW.state.moreMenuOpen = null;
  MW.state.seasonMoreOpen = null;
  const prev = MW.state.navStack.pop();
  MW.state.expandedSeason = null;
  renderRoute(prev || {type:"home"});
  window.scrollTo({top:0, behavior:"smooth"});
}

function goHome() {
  MW.state.moreMenuOpen = null;
  MW.state.seasonMoreOpen = null;
  MW.state.navStack = [];
  MW.state.expandedSeason = null;
  renderRoute({type:"home"});
  window.scrollTo({top:0, behavior:"smooth"});
}

/* ===== Home ===== */

/* ── Hero Banner ────────────────────────────────── */

function pickHeroItem(items, continueItems, hasQuery) {
  if (hasQuery) return null;
  const ci = continueItems[0];
  if (ci) return ci.item;
  const pick = items[Math.floor(Math.random() * Math.min(3, items.length))];
  return pick || items[0] || null;
}

function renderHero(item) {
  if (!item) return '';
  const t = tmdb(item);
  const d = douban(item);
  const backdropRaw = t.backdrop_url || artworkUrl(item, "thumb") || t.poster_url || artworkUrl(item, "poster");
  const posterRaw = artworkUrl(item, "poster") || t.poster_url;
  const heroRating = d.rating || t.rating || "";
  const genres = (t.genres || []).slice(0, 3);
  const isShow = item.type === "show";
  const firstEp = isShow ? findFirstEpisode(item) : null;
  const hist = getItemHistory(item);
  const playAction = isShow && firstEp
    ? "playMedia('" + escapeJs(firstEp.ep.path) + "'," + episodeEntry(item, firstEp.season, firstEp.ep, firstEp.season.title + " · " + firstEp.ep.title) + ")"
    : hist ? "playItemHistory('" + item.id + "')" : "openDetail('" + item.id + "')";
  const playLabel = isShow && hist ? "▶ 继续播放" : (hist ? "▶ 继续播放" : "▶ 立即观看");

  const typeLabel = isShow ? ((item.season_count || 0) + ' 季 · ' + (item.episode_count || 0) + ' 集') : '电影';

  // Page-level full-viewport backdrop (image + gradient overlay, 100vh)
  let pageBg = '';
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
    + '<h1 class="hero-title">' + escapeHtml(titleOf(item)) + '</h1>'
    + '<div class="hero-meta">'
    + (heroRating ? '<span class="rating-badge lg' + (d.rating ? ' douban' : '') + '">★ ' + Number(heroRating).toFixed(1) + '</span>' : '')
    + (item.year ? '<span class="year">' + escapeHtml(item.year) + '</span>' : '')
    + '<span class="year">' + escapeHtml(typeLabel) + '</span>'
    + (genres.length ? genres.map(g => '<span class="genre-tag">' + escapeHtml(g) + '</span>').join('') : '')
    + '</div>'
    + '<div class="hero-overview">' + escapeHtml(t.overview || d.synopsis || "") + '</div>'
    + '<div class="hero-actions">'
    + '<button class="cta-btn" onclick="event.stopPropagation();' + playAction + '">' + playLabel + '</button>'
    + '<button class="cta-btn secondary' + (isFavorite(item.id) ? ' favorited' : '') + '" onclick="event.stopPropagation();toggleFavorite(\'' + item.id + '\')">' + (isFavorite(item.id) ? '♥ 已收藏' : '♡ 收藏') + '</button>'
    + '<button class="cta-btn secondary" onclick="event.stopPropagation();openDetail(\'' + item.id + '\')">详情</button>'
    + '</div></div>'
    + (posterRaw ? '<div class="hero-poster"><img src="' + posterRaw + '" loading="lazy" alt=""></div>' : '')
    + '</div>';
}

/* ── Horizontal Scroll Row ──────────────────────── */

function renderRowSection(title, items, renderFn, moreKey) {
  if (!items || !items.length) return '';
  const moreLink = moreKey ? ' onclick="setTab(\'' + moreKey + '\')"' : '';
  return '<section class="row-section">'
    + '<div class="row-header"><h2>' + escapeHtml(title) + '</h2>'
    + (moreLink ? '<span class="row-more"' + moreLink + '>查看全部 →</span>' : '')
    + '</div>'
    + '<div class="row-shell"><div class="row-scroll">'
    + items.map(renderFn).join('')
    + '</div></div></section>';
}

/* ── Home Page ──────────────────────────────────── */

function renderHome() {
  MW.state.currentView = {type:"home"};
  renderCategoryTabs();
  renderBreadcrumb();

  if (!MW.state.library.items.length) {
    app.innerHTML = '<section class="section"><div class="empty">暂无内容。请确认路径正确，然后点击"扫描"。</div></section>';
    return;
  }

  const items = getFilteredItems();
  if (!items.length) {
    const emptyMsg = MW.state.activeTab === "favorites" ? "暂无收藏内容" : "没有匹配的内容。试试其他分类或搜索词。";
    app.innerHTML = '<section class="section"><div class="empty">' + emptyMsg + '</div></section>';
    return;
  }

  const hasQuery = search.value.trim().length > 0;
  const continueItems = hasQuery ? [] : getContinueItems();

  // ── "全部" tab → Hero + dynamic category row layout ────
  if (MW.state.activeTab === "all" && !hasQuery) {
    const heroItem = pickHeroItem(items, continueItems, hasQuery);

    const catStats = MW.state.library.stats?.categories || [];
    const recent = [...items].sort((a, b) => (b.updated_at || b.created_at || 0) - (a.updated_at || a.created_at || 0)).slice(0, 20);

    let html = renderHero(heroItem);

    if (continueItems.length > 0) {
      html += renderRowSection("继续观看", continueItems, renderContinueCard);
    }
    // Favorites row
    const favItems = items.filter(i => MW.state.favoritesCache.includes(i.id));
    if (favItems.length > 0) {
      html += renderRowSection("收藏", favItems, renderHomeCard, "favorites");
    }
    // Dynamic category sections — ONLY from library.stats.categories, no media_type sections
    for (const cat of catStats) {
      const catItems = items.filter(i => i.category_key === cat.key);
      if (catItems.length > 0) {
        html += renderRowSection(cat.name, catItems, renderHomeCard, "cat:" + cat.key);
      }
    }
    if (recent.length > 0) {
      html += renderRowSection("最近添加", recent.slice(0, 15), renderHomeCard);
    }

    app.innerHTML = html;
    return;
  }

  // ── Category-specific tab or search → grid layout ─────
  let html = '';

  if (continueItems.length > 0) {
    html += '<section class="section">'
      + '<div class="section-header"><h2>继续观看</h2><small>' + continueItems.length + ' 项</small></div>'
      + '<div class="continue-strip">'
      + continueItems.map(renderContinueCard).join('')
      + '</div></section>';
  }

  if (hasQuery) {
    html += '<section class="section">'
      + '<div class="section-header"><h2>搜索结果</h2><small>' + items.length + ' 项</small></div>'
      + '<div class="grid">' + items.map(renderHomeCard).join('') + '</div></section>';
  } else {
    const sectionTitle = MW.state.activeTab === "favorites" ? "收藏" : escapeHtml(items[0]?.category_name || '');
    html += '<section class="section">'
      + '<div class="section-header"><h2>' + sectionTitle + '</h2><small>' + items.length + ' 项</small></div>'
      + '<div class="grid">' + items.map(renderHomeCard).join('') + '</div></section>';
  }

  app.innerHTML = html;
}

/* ===== Card Overlay ===== */

function primaryPlayAction(item) {
  const hist = getItemHistory(item);
  if (hist) return "playItemHistory('" + item.id + "')";
  if (item.type === "movie" && item.path) {
    const entry = "{media_id:'" + item.id + "',type:'movie',path:'" + escapeJs(item.path) + "',title:'" + escapeJs(titleOf(item)) + "',show_title:'" + escapeJs(titleOf(item)) + "',label:'电影',short_label:'电影'}";
    return "playMedia('" + escapeJs(item.path) + "'," + entry + ")";
  }
  if (item.type === "show") {
    const firstEp = findFirstEpisode(item);
    if (firstEp) {
      return "playMedia('" + escapeJs(firstEp.ep.path) + "'," + episodeEntry(item, firstEp.season, firstEp.ep, firstEp.season.title + " · " + firstEp.ep.title) + ")";
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
  const q = search.value.trim();
  const fav = isFavorite(item.id);
  const t = tmdb(item);
  const d = douban(item);
  const score = d.rating || t.rating || "";
  const epCount = item.type === "show" ? (item.episode_count || 0) : 0;
  const showCount = item.type === "show" && epCount > 0;
  const badges = (score ? '<div class="card-badge-score">★ ' + Number(score).toFixed(1) + '</div>' : '')
    + (showCount ? '<div class="card-badge-episodes">' + epCount + ' 集</div>' : '')
    + (item.year ? '<div class="card-badge-year">' + escapeHtml(item.year) + '</div>' : '');
  return '<article class="card' + (fav ? ' is-fav' : '') + '" onclick="openDetail(\'' + item.id + '\')">'
    + '<div class="card-poster">'
    + (fav ? '<div class="fav-badge">♥</div>' : '')
    + badges
    + (artworkUrl(item, "poster")
      ? '<img src="' + artworkUrl(item, "poster") + '" loading="lazy" onerror="this.parentElement.innerHTML=\'<div class=\\\'placeholder\\\'>' + escapeHtml(titleOf(item)) + '</div>\'">'
      : '<div class="placeholder">' + escapeHtml(titleOf(item)) + '</div>')
    + renderCardOverlay(item)
    + '</div>'
    + '<div class="card-body"><h4 class="card-title">' + highlightText(titleOf(item), q) + '</h4></div>'
    + '</article>';
}

function renderContinueCard(entry) {
  const {item, hist} = entry;
  const title = hist.show_title || hist.title || titleOf(item);
  const label = hist.short_label || hist.label || "";
  const isShow = item.type === "show";
  // Episode context: if hist has episode_number/season_number, show it
  const epContext = hist.season_number ? 'S' + String(hist.season_number).padStart(2,'0') + 'E' + String(hist.episode_number || 0).padStart(2,'0') : label;
  let progressPct = 0;
  if (isShow) {
    const totalEps = item.episode_count || 0;
    const watchedEps = (item.seasons || []).reduce((sum, s) =>
      sum + (s.episodes || []).filter(ep => MW.state.historyCache[ep.id]).length, 0);
    progressPct = totalEps ? Math.round(watchedEps / totalEps * 100) : 0;
  }
  const histEntry = "{media_id:'" + item.id + "',type:'" + item.type + "',path:'" + escapeJs(hist.path) + "',title:'" + escapeJs(title) + "',show_title:'" + escapeJs(hist.show_title || title) + "',label:'" + escapeJs(epContext) + "',short_label:'" + escapeJs(epContext) + "'}";
  const t = tmdb(item);
  const d = douban(item);
  const score = d.rating || t.rating || "";
  return '<article class="card continue-card" onclick="playMedia(\'' + escapeJs(hist.path) + '\',' + histEntry + ')">'
    + '<div class="card-poster">'
    + (score ? '<div class="card-badge-score">★ ' + Number(score).toFixed(1) + '</div>' : '')
    + (artworkUrl(item, "poster")
      ? '<img src="' + artworkUrl(item, "poster") + '" loading="lazy" onerror="this.parentElement.innerHTML=\'<div class=\\\'placeholder\\\'>' + escapeHtml(title) + '</div>\'">'
      : '<div class="placeholder">' + escapeHtml(title) + '</div>')
    + '<div class="card-overlay">'
    + '<div class="poster-actions"><button class="poster-play" onclick="event.stopPropagation();playMedia(\'' + escapeJs(hist.path) + '\',' + histEntry + ')" title="继续播放">▶</button></div>'
    + '</div>'
    + (progressPct > 0 ? '<div class="card-progress"><div class="card-progress-bar" style="width:' + progressPct + '%"></div></div>' : '')
    + '</div>'
    + '<div class="card-body">'
    + '<div class="continue-kicker">▶ ' + escapeHtml(isShow ? epContext : '继续观看') + '</div>'
    + '<h4 class="card-title">' + escapeHtml(title) + '</h4></div>'
    + '</article>';
}

/* ===== Home Render ===== */

function showSkeleton() {
  const card = '<div class="skeleton-card"><div class="skeleton-poster skeleton"></div><div class="skeleton-title skeleton"></div></div>';
  app.innerHTML = '<section class="section loading-section"><div class="grid">' + card.repeat(12) + '</div></section>';
}

function openDetail(id) { navigateTo({type:"detail", id}); }
function toggleSeason(showId, seasonNumber) {
  if (MW.state.expandedSeason === showId + "|" + seasonNumber) { MW.state.expandedSeason = null; renderRoute(MW.state.currentView); return; }
  MW.state.expandedSeason = showId + "|" + seasonNumber;
  renderRoute(MW.state.currentView);
  requestAnimationFrame(() => {
    const el = document.querySelector('.season-expanded-wrap');
    if (el) el.scrollIntoView({behavior:"smooth", block:"start"});
  });
}

/* ===== Playback ===== */

async function playMedia(path, entry, player) {
  const route = {...MW.state.currentView};
  const body = {path};
  if (player) body.player = player;
  // Send episode context so backend can monitor PotPlayer and sync actual last played file
  if (entry) {
    body.media_id = entry.media_id;
    body.episode_id = entry.episode_id;
    body.season_id = entry.season_id;
    body.season_number = entry.season_number;
    body.episode_number = entry.episode_number;
    body.show_title = entry.show_title;
  }
  const res = await fetch("/api/play", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
  const data = await res.json().catch(() => ({}));
  if (!data.ok) return alert(data.error || "播放失败");
  if (entry) { recordPlay(entry); startHistoryPolling(); renderRoute(route); }
}

function playItemHistory(itemId) {
  const hist = MW.state.historyCache[itemId];
  if (hist) playMedia(hist.path, hist);
}

/* ===== More Menu ===== */

function toggleMore(id, e) { if (e) e.stopPropagation(); MW.state.moreMenuOpen = MW.state.moreMenuOpen === id ? null : id; renderRoute(MW.state.currentView); }
function toggleSeasonMore(showId, sn, e) {
  if (e) e.stopPropagation();
  const id = "smore-" + showId + "-" + sn;
  MW.state.seasonMoreOpen = MW.state.seasonMoreOpen === id ? null : id;
  renderRoute(MW.state.currentView);
}

function moreMenuHtml(item, extraActions) {
  const id = item.id;
  const open = MW.state.moreMenuOpen === id;
  let actions = '';
  if (MW.state.players && MW.state.players.length > 1) {
    actions += MW.state.players.map(p => '<button onclick="playMedia(\'' + escapeJs(item.path) + '\',{media_id:\'' + item.id + '\'},\'' + escapeJs(p.name) + '\')">用 ' + escapeHtml(p.name) + ' 播放</button>').join("");
  }
  if (extraActions) actions += extraActions;
  return '<div class="more-wrap"><button class="ghost more-btn" onclick="toggleMore(\'' + id + '\',event)">···</button>' + (open ? '<div class="more-dropdown" onclick="event.stopPropagation()">' + actions + '</div>' : '') + '</div>';
}

/* ===== Detail Page ===== */

function renderGenreTags(item) {
  const t = tmdb(item);
  const genres = t.genres || [];
  return genres.map(g => '<span class="genre-tag">' + escapeHtml(g) + '</span>').join('');
}

function renderPrimaryMeta(item) {
  const parts = [];
  if (item.year) parts.push('<span class="year">' + escapeHtml(item.year) + '</span>');
  const dualHtml = renderDualRating(item);
  if (dualHtml) parts.push(dualHtml);
  if (item.type === "show") {
    parts.push('<span class="year">' + (item.season_count || 0) + ' 季 · ' + (item.episode_count || 0) + ' 集</span>');
  }
  return parts.join('<span class="sep">·</span>');
}

function renderDoubanTags(item) {
  const d = douban(item);
  const abstract = d.abstract || "";
  const abstract_2 = d.abstract_2 || "";
  const cast = creditsCast(item);
  if (!abstract && !abstract_2 && !cast.length) return '';
  // Skip douban abstract parts that already appear as TMDB genres
  const t = tmdb(item);
  const existingGenres = (t.genres || []).map(g => g.toLowerCase());
  let tags = [];
  if (abstract) {
    abstract.split(' / ').forEach(part => {
      part = part.trim();
      if (!part) return;
      if (existingGenres.includes(part.toLowerCase())) return;
      if (/^\d+分钟$/.test(part)) {
        tags.push('<span class="genre-tag douban-tag runtime">' + escapeHtml(part) + '</span>');
      } else {
        tags.push('<span class="genre-tag douban-tag">' + escapeHtml(part) + '</span>');
      }
    });
  }
  let html = '<div class="douban-meta">';
  if (tags.length) html += '<div class="genre-tags douban-tags">' + tags.join('') + '</div>';
  if (abstract_2) {
    html += '<div class="douban-cast"><span class="cast-label">演员</span> <span class="cast-names">' + escapeHtml(abstract_2.replace(/ \/ /g, ' · ')) + '</span></div>';
  } else if (cast.length) {
    html += '<div class="douban-cast"><span class="cast-label">演员</span> <span class="cast-names">' + escapeHtml(cast.slice(0, 8).map(c => c.person?.name).filter(Boolean).join(' · ')) + '</span></div>';
  }
  html += '</div>';
  return html;
}

function detailHero(item, bodyHtml, castHtml) {
  const bg = backdropUrl(item);
  const poster = tmdb(item).poster_url || artworkUrl(item, "poster") || artworkUrl(item, "thumb");

  // Full-viewport backdrop layer
  let pageBg = '';
  if (bg) {
    pageBg += '<div class="page-backdrop">'
      + '<div class="page-backdrop-img" style="background-image:url(\'' + bg + '\')"></div>'
      + '<div class="page-backdrop-overlay"></div>'
      + '</div>';
  }

  return pageBg
    + '<section class="detail-hero cinematic-detail">'
    + '<div class="detail-hero-content">'
    + '<button class="back-hero-btn" onclick="event.stopPropagation();goBackSmart()" title="返回" aria-label="返回">'
    + '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>'
    + '</button>'
    + '<div class="detail-poster">'
    + (poster ? '<img src="' + poster + '" loading="lazy">' : '<div class="placeholder">' + escapeHtml(titleOf(item)) + '</div>')
    + '</div>'
    + '<div class="detail-info">' + bodyHtml
    + (castHtml ? '<div class="detail-cast-inline">' + castHtml + '</div>' : '')
    + '</div>'
    + '</div>'
    + '</section>';
}

function renderMovieDetail(item) {
  MW.state.currentView = {type:"detail", id:item.id};
  renderCategoryTabs();
  renderBreadcrumb();
  const meta = tmdb(item);
  const overview = meta.overview;
  const origTitle = meta.original_title && meta.original_title !== titleOf(item) ? meta.original_title : "";
  const hist = getItemHistory(item);
  const entry = "{media_id:'" + item.id + "',type:'movie',path:'" + escapeJs(item.path) + "',title:'" + escapeJs(titleOf(item)) + "',show_title:'" + escapeJs(titleOf(item)) + "',label:'电影',short_label:'电影'}";
  const d = douban(item);
  const cast = (item.metadata?.credits?.cast || []).filter(c => c.person?.id);
  const more = moreMenuHtml(item, '<button onclick="openFolder(\'' + escapeJs(item.folder) + '\')">打开文件夹</button><button onclick="updateSingleItem(\'' + item.id + '\')">更新此项目</button><button onclick="openDoubanSetting(\'' + item.id + '\',\'' + escapeJs(d.douban_id || "") + '\')">' + (d.douban_id ? '修改豆瓣ID' : '设置豆瓣ID') + '</button>');

  const body = '<h1>' + escapeHtml(titleOf(item)) + '</h1>'
    + (origTitle ? '<div class="detail-subtitle">' + escapeHtml(origTitle) + '</div>' : '')
    + '<div class="detail-primary-meta">' + renderPrimaryMeta(item) + '</div>'
    + '<div class="genre-tags">' + renderGenreTags(item) + '</div>'
    + renderDoubanTags(item)
    + (overview ? '<div class="overview">' + escapeHtml(overview) + '</div>' : '')
    + starRatingWidget(item)
    + '<div class="detail-actions">'
    + (hist ? '<button class="cta-btn" onclick="event.stopPropagation();playItemHistory(\'' + item.id + '\')">▶ 继续播放</button>' : '<button class="cta-btn" onclick="event.stopPropagation();playMedia(\'' + escapeJs(item.path) + '\',' + entry + ')">▶ 播放</button>')
    + more
    + '</div>';

  const castHtml = renderCastSection(cast);
  app.innerHTML = detailHero(item, body, castHtml);
}

function renderShowDetail(item) {
  MW.state.currentView = {type:"detail", id:item.id};
  renderCategoryTabs();
  renderBreadcrumb();
  const meta = tmdb(item);
  const overview = meta.overview;
  const origTitle = meta.original_title && meta.original_title !== titleOf(item) ? meta.original_title : "";
  const hist = getItemHistory(item);
  const dd = douban(item);
  const moreActions = '<button onclick="openFolder(\'' + escapeJs(item.folder) + '\')">打开文件夹</button>'
    + '<button onclick="updateSingleItem(\'' + item.id + '\')">更新此项目</button>'
    + '<button onclick="openDoubanSetting(\'' + item.id + '\',\'' + escapeJs(dd.douban_id || "") + '\')">' + (dd.douban_id ? '修改豆瓣ID' : '设置豆瓣ID') + '</button>';
  const more = moreMenuHtml(item, moreActions);
  const firstEp = findFirstEpisode(item);
  const firstEntry = firstEp ? episodeEntry(item, firstEp.season, firstEp.ep, firstEp.season.title + " · " + firstEp.ep.title) : "";
  const cast = (item.metadata?.credits?.cast || []).filter(c => c.person?.id);

  const body = '<h1>' + escapeHtml(titleOf(item)) + '</h1>'
    + (origTitle ? '<div class="detail-subtitle">' + escapeHtml(origTitle) + '</div>' : '')
    + '<div class="detail-primary-meta">' + renderPrimaryMeta(item) + '</div>'
    + '<div class="genre-tags">' + renderGenreTags(item) + '</div>'
    + renderDoubanTags(item)
    + (overview ? '<div class="overview">' + escapeHtml(overview) + '</div>' : '')
    + starRatingWidget(item)
    + '<div class="detail-actions">'
    + (hist ? '<button class="cta-btn" onclick="event.stopPropagation();playItemHistory(\'' + item.id + '\')">▶ 继续播放</button>' : '')
    + (firstEntry ? '<button class="cta-btn" onclick="event.stopPropagation();playMedia(\'' + escapeJs(firstEp.ep.path) + '\',' + firstEntry + ')">▶ 播放第1集</button>' : '')
    + '<button class="cta-btn secondary' + (isFavorite(item.id) ? ' favorited' : '') + '" onclick="event.stopPropagation();toggleFavorite(\'' + item.id + '\')">' + (isFavorite(item.id) ? '♥' : '♡') + ' 收藏</button>'
    + more
    + '</div>';

  const castHtml = renderCastSection(cast);
  const isExpanded = (snum) => MW.state.expandedSeason === item.id + "|" + snum;
  const seasonCards = (item.seasons || []).map((s, i) => renderSeasonCard(item, s, isExpanded(s.season_number)));

  let seasonHtml = '<section class="section">'
    + '<div class="section-header"><h2>季</h2><small>' + (item.season_count || 0) + ' 季 · ' + (item.episode_count || 0) + ' 集</small></div>'
    + '<div class="season-wall">'
    + seasonCards.join("")
    + '</div>';

  const expandedSeasonData = (item.seasons || []).filter(s => isExpanded(s.season_number));
  if (expandedSeasonData.length > 0) {
    const es = expandedSeasonData[0];
    seasonHtml += '<div class="season-expanded-wrap">'
      + '<div class="season-expanded-header">'
      + '<span>' + escapeHtml(es.title) + ' · 剧集列表</span>'
      + '<button class="ghost" onclick="toggleSeason(\'' + item.id + '\',' + es.season_number + ')" style="font-size:12px">收起</button>'
      + '</div>'
      + renderInlineEpisodes(item, es)
      + '</div>';
  }

  seasonHtml += '</section>';
  app.innerHTML = detailHero(item, body, castHtml) + seasonHtml;
}

function findFirstEpisode(show) {
  if (!show?.seasons?.length) return null;
  for (const s of show.seasons) {
    if (s.episodes?.length) return {season: s, ep: s.episodes[0]};
  }
  return null;
}

/* ===== Season Card (enhanced) ===== */

function renderSeasonCard(show, season, expanded) {
  const epWatched = season.episodes.filter(ep => MW.state.historyCache[ep.id]).length;
  const progressPct = season.episode_count ? Math.round(epWatched / season.episode_count * 100) : 0;
  const sMeta = seasonDouban(season);
  const tmdbSeasonData = seasonTmdb(season);
  const seasonYear = sMeta.air_date ? sMeta.air_date.toString().slice(0,4) : season.year || show.year || "";
  const seasonPoster = tmdbSeasonData.poster_url || sMeta.poster_url || artworkUrl(season, "poster") || "";
  const moreId = "smore-" + show.id + "-" + season.season_number;
  const showMore = MW.state.seasonMoreOpen === moreId;
  const moreHtml = '<div class="season-more-wrap" onclick="event.stopPropagation()">'
    + '<button class="season-more-btn" onclick="event.stopPropagation();toggleSeasonMore(\'' + show.id + '\',' + season.season_number + ')">···</button>'
    + (showMore ? '<div class="season-more-dropdown">'
      + '<button onclick="event.stopPropagation();updateSingleItem(\'' + show.id + '\')">更新此季</button>'
      + '<button onclick="event.stopPropagation();toggleSeasonMore(\'' + show.id + '\',' + season.season_number + ');navigateTo({type:\'season\', showId:\'' + show.id + '\', seasonNumber:' + season.season_number + '})">季详情</button>'
      + '</div>' : '')
    + '</div>';
  return '<article class="card season-card' + (expanded ? ' season-expanded' : '') + (showMore ? ' smore-open' : '') + '" onclick="toggleSeason(\'' + show.id + '\',' + season.season_number + ')">'
    + '<div class="card-poster">'
    + (seasonPoster
      ? '<img src="' + seasonPoster + '" loading="lazy">'
      : '<div class="placeholder">' + escapeHtml(titleOf(show)) + '</div>')
    + '</div>'
    + '<div class="card-body"><h4 class="card-title" style="display:inline">' + escapeHtml(season.title) + '</h4>'
    + moreHtml
    + '<div class="season-meta">'
    + (seasonYear ? '<span class="year">' + seasonYear + '</span>' : '')
    + (season.episode_count ? '<span>' + season.episode_count + ' 集</span>' : '')
    + (sMeta.rating ? '<span class="rating-badge douban sm">豆瓣 ' + Number(sMeta.rating).toFixed(1) + '</span>' : '')
    + (tmdbSeasonData.rating ? '<span class="rating-badge tmdb sm">TMDB ' + Number(tmdbSeasonData.rating).toFixed(1) + '</span>' : '')
    + '</div>'
    + (progressPct > 0
      ? '<div class="season-progress"><div class="season-progress-bar" style="width:' + progressPct + '%"></div></div><div class="season-progress-text">已看 ' + epWatched + '/' + (season.episode_count || 0) + '</div>'
      : '')
    + '</div></article>';
}

function renderInlineEpisodes(show, season) {
  const sMeta = seasonDouban(season);
  const tmdbSeasonData = seasonTmdb(season);
  const seasonSynopsis = sMeta.synopsis || tmdbSeasonData.overview || "";
  const seasonPoster = tmdbSeasonData.poster_url || sMeta.poster_url || artworkUrl(season, "poster") || "";
  let detailHtml = '';
  if (seasonSynopsis || seasonPoster || sMeta.cast_info || sMeta.air_date) {
    detailHtml = '<div class="season-detail-card">'
      + (seasonPoster ? '<img class="season-detail-poster" src="' + seasonPoster + '" loading="lazy">' : '')
      + '<div class="season-detail-body">'
      + (seasonSynopsis ? '<div class="season-detail-synopsis">' + escapeHtml(seasonSynopsis) + '</div>' : '')
      + (sMeta.cast_info ? '<div class="season-detail-cast"><span class="cast-label">主演</span> <span>' + escapeHtml(sMeta.cast_info.replace(/\s*\/\s*/g, ' · ')) + '</span></div>' : '')
      + (sMeta.air_date ? '<div class="season-detail-air"><span class="cast-label">年份</span> <span>' + escapeHtml(sMeta.air_date) + '</span></div>' : '')
      + '</div></div>';
  }
  return '<div class="inline-episodes">'
    + detailHtml
    + '<div class="episode-list">'
    + (season.episodes || []).map(ep => renderEpisodeCard(show, season, ep)).join("")
    + '</div></div>';
}

/* ===== Season Detail ===== */

function renderSeasonDetail(show, season) {
  MW.state.currentView = {type:"season", showId:show.id, seasonNumber:season.season_number};
  renderCategoryTabs();
  renderBreadcrumb();

  const firstEp = (season.episodes || [])[0];
  const firstEntry = firstEp ? episodeEntry(show, season, firstEp, season.title + " · " + firstEp.title) : "";
  const t = tmdb(show);
  const sMeta = seasonDouban(season);
  const tmdbSeasonData = seasonTmdb(season);
  const seasonRating = sMeta.rating || tmdbSeasonData.rating || "";
  const seasonYear = sMeta.air_date ? sMeta.air_date.toString().slice(0,4) : season.year || show.year || "";
  const seasonSynopsis = sMeta.synopsis || tmdbSeasonData.overview || "";
  const origTitle = t.original_title && t.original_title !== titleOf(show) ? t.original_title : "";

  const seasonPosterUrl = tmdbSeasonData.poster_url || sMeta.poster_url || t.poster_url;
  const seasonHero = {
    ...season,
    display_title: titleOf(show) + " · " + season.title,
    title: titleOf(show) + " · " + season.title,
    metadata: {
      ...show.metadata,
      tmdb: {
        ...t,
        poster_url: seasonPosterUrl,
        backdrop_url: t.backdrop_url || t.poster_url,
      }
    }
  };

  const metaParts = [];
  if (seasonYear) metaParts.push('<span class="year">' + escapeHtml(seasonYear) + '</span>');
  if (sMeta.rating) metaParts.push('<span class="rating-badge douban">豆瓣 ' + Number(sMeta.rating).toFixed(1) + '</span>');
  if (tmdbSeasonData.rating) metaParts.push('<span class="rating-badge tmdb">TMDB ' + Number(tmdbSeasonData.rating).toFixed(1) + '</span>');
  if (sMeta.rating_count) metaParts.push('<span class="rating-badge douban-count">' + Number(sMeta.rating_count).toLocaleString() + ' 评</span>');
  if (!sMeta.rating && !tmdbSeasonData.rating && seasonRating) metaParts.push('<span class="rating-badge sm">' + Number(seasonRating).toFixed(1) + '</span>');
  metaParts.push('<span class="year">' + (season.episode_count || 0) + ' 集</span>');

  const hist = getItemHistory(show);
  const dd = douban(show);
  const moreActions = '<button onclick="openFolder(\'' + escapeJs(show.folder) + '\')">打开文件夹</button>'
    + '<button onclick="updateSingleItem(\'' + show.id + '\')">更新此项目</button>'
    + '<button onclick="openDoubanSetting(\'' + show.id + '\',\'' + escapeJs(dd.douban_id || "") + '\')">' + (dd.douban_id ? '修改豆瓣ID' : '设置豆瓣ID') + '</button>';
  const more = moreMenuHtml(show, moreActions);

  const body = '<h1>' + escapeHtml(season.title) + '</h1>'
    + (origTitle ? '<div class="detail-subtitle">' + escapeHtml(origTitle) + '</div>' : '')
    + '<div class="detail-primary-meta">' + metaParts.join('<span class="sep">·</span>') + '</div>'
    + '<div class="genre-tags">' + renderGenreTags(show) + '</div>'
    + renderSeasonDoubanTags(show, season)
    + (seasonSynopsis ? '<div class="overview">' + escapeHtml(seasonSynopsis) + '</div>' : '')
    + starRatingWidget(show)
    + '<div class="detail-actions">'
    + (hist ? '<button class="cta-btn" onclick="event.stopPropagation();playItemHistory(\'' + show.id + '\')">▶ 继续播放</button>' : '')
    + (firstEp ? '<button class="cta-btn" onclick="playMedia(\'' + escapeJs(firstEp.path) + '\',' + firstEntry + ')">▶ 播放第1集</button>' : '<button class="cta-btn" disabled>无剧集</button>')
    + '<button class="cta-btn secondary' + (isFavorite(show.id) ? ' favorited' : '') + '" onclick="event.stopPropagation();toggleFavorite(\'' + show.id + '\')">' + (isFavorite(show.id) ? '♥' : '♡') + ' 收藏</button>'
    + '<button class="cta-btn secondary" onclick="event.stopPropagation();navigateTo({type:\'detail\', id:\'' + show.id + '\'})">← 返回剧集</button>'
    + more
    + '</div>';

  app.innerHTML = detailHero(seasonHero, body, '')
    + '<section class="section">'
    + '<div class="section-header"><h2>剧集</h2><small>' + (season.episode_count || 0) + ' 集</small></div>'
    + '<div class="episode-list">'
    + (season.episodes || []).map(ep => renderEpisodeCard(show, season, ep)).join("")
    + '</div></section>';
}

function renderSeasonDoubanTags(show, season) {
  const sMeta = seasonDouban(season);
  const d = douban(show);
  const abstract = d.abstract || "";
  let tags = [];
  if (abstract) {
    abstract.split(' / ').forEach(part => {
      part = part.trim();
      if (!part) return;
      tags.push('<span class="genre-tag douban-tag' + (/^\d+分钟$/.test(part) ? ' runtime' : '') + '">' + escapeHtml(part) + '</span>');
    });
  }
  let html = '<div class="douban-meta">';
  if (tags.length) html += '<div class="genre-tags douban-tags">' + tags.join('') + '</div>';
  if (sMeta.cast_info) {
    html += '<div class="douban-cast"><span class="cast-label">演员</span> <span class="cast-names">' + escapeHtml(sMeta.cast_info.replace(/ \/ /g, ' · ')) + '</span></div>';
  } else if (d.abstract_2) {
    html += '<div class="douban-cast"><span class="cast-label">演员</span> <span class="cast-names">' + escapeHtml(d.abstract_2.replace(/ \/ /g, ' · ')) + '</span></div>';
  }
  html += '</div>';
  return html;
}

/* ===== Episode Entry ===== */

function episodeEntry(show, season, ep, label) {
  return "{media_id:'" + show.id + "',episode_id:'" + ep.id + "',season_id:'" + season.id + "',type:'episode',path:'" + escapeJs(ep.path) + "',title:'" + escapeJs(ep.title) + "',show_title:'" + escapeJs(titleOf(show)) + "',season_number:" + season.season_number + ",episode_number:" + (ep.episode_number || 0) + ",label:'" + escapeJs(label) + "',short_label:'S" + String(season.season_number).padStart(2,"0") + "E" + String(ep.episode_number || 0).padStart(2,"0") + "'}";
}

/* ===== Episode Card (compact row) ===== */

function renderEpisodeCard(show, season, ep) {
  const hist = getItemHistory(show);
  const active = hist && hist.episode_id === ep.id;
  const label = season.title + " · " + ep.title;
  const entry = episodeEntry(show, season, ep, label);
  const epHist = MW.state.historyCache[ep.id];
  const epm = ep.metadata?.tmdb || {};
  const stillSrc = epm.still_url || artworkUrl(ep, "thumb") || artworkUrl(ep, "poster");
  const epNum = "S" + String(season.season_number).padStart(2,"0") + "E" + String(ep.episode_number || 0).padStart(2,"0");
  const epName = epm.title || ep.title || ep.filename || epNum;
  const epOverview = epm.overview || ep.overview || "";
  const epRating = epm.rating ? '<span class="ep-badge rating-badge sm">★ ' + Number(epm.rating).toFixed(1) + '</span>' : '';
  const epRuntime = epm.runtime ? '<span class="ep-badge">' + epm.runtime + '分钟</span>' : '';

  return '<div class="episode-row' + (active ? ' active-episode' : '') + '" onclick="playMedia(\'' + escapeJs(ep.path) + '\',' + entry + ')">'
    + '<div class="episode-row-thumb">'
    + (stillSrc
      ? '<img src="' + stillSrc + '" loading="lazy" onerror="this.parentElement.innerHTML=\'<div class=\\\'placeholder episode-placeholder\\\'>' + escapeHtml(epNum) + '</div>\'">'
      : '<div class="placeholder episode-placeholder">' + escapeHtml(epNum) + '</div>')
    + '<div class="play-badge"><span>▶</span></div>'
    + '</div>'

    + '<div class="episode-row-body">'
    + '<div class="episode-row-top">'
    + '<span class="episode-row-num' + (active ? ' active-num' : '') + '">' + epNum + '</span>'
    + '<span class="episode-row-title">' + escapeHtml(epName) + '</span>'
    + '<span class="episode-row-meta">' + epRating + epRuntime + '</span>'
    + '</div>'
    + (epOverview ? '<div class="episode-row-overview">' + escapeHtml(epOverview) + '</div>' : '')
    + (epHist ? '<div class="episode-row-progress"><div class="bar" style="width:100%"></div></div>' : '')
    + '</div>'

    + '<div class="episode-row-play"><button onclick="event.stopPropagation();playMedia(\'' + escapeJs(ep.path) + '\',' + entry + ')" title="播放">▶</button></div>'
    + '</div>';
}

/* ===== Settings ===== */

let settingDoubanId = "";
let settingDoubanItemId = "";

function openDoubanSetting(itemId, currentDoubanId) {
  MW.state.moreMenuOpen = null;
  MW.state.seasonMoreOpen = null;
  settingDoubanItemId = itemId;
  settingDoubanId = currentDoubanId || "";
  renderSettings();
}

async function saveDoubanId() {
  const id = settingDoubanId.trim();
  const itemId = settingDoubanItemId;
  if (!itemId) return;
  const rating = document.getElementById("doubanRating")?.value?.trim();
  const synopsis = document.getElementById("doubanSynopsis")?.value?.trim();
  const body = {douban_id: id};
  if (rating) body.rating = parseFloat(rating);
  if (synopsis) body.synopsis = synopsis;
  const res = await fetch("/api/metadata/douban/" + itemId, {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
  const data = await res.json();
  if (data.douban) {
    showToast("豆瓣数据已更新");
  } else if (id) {
    showToast("未找到该豆瓣ID的数据（已保存ID，可手动输入评分）", 4000);
  } else {
    showToast("已清除豆瓣ID");
  }
  settingDoubanItemId = "";
  settingDoubanId = "";
  const libRes = await fetch("/api/library");
  MW.state.library = await libRes.json();
  navigateTo({type:"detail", id: itemId});
}

function renderSettings() {
  stopHistoryPolling();
  MW.state.navStack = [];
  renderCategoryTabs();
  renderBreadcrumb();
  const catKeys = Object.keys(MW.state.categoriesConfig);
  const rows = catKeys.map((key, i) => '<div class="settings-cat-row"><input class="sc-folder" value="' + escapeHtml(key) + '" placeholder="文件夹名"><input class="sc-name" value="' + escapeHtml(MW.state.categoriesConfig[key].name) + '" placeholder="显示名"><button class="ghost" onclick="this.closest(\'.settings-cat-row\').remove()">✕</button></div>').join("");

  let doubanSection = '';
  if (settingDoubanItemId) {
    const item = findItem(settingDoubanItemId);
    const itemName = item ? titleOf(item) : settingDoubanItemId;
    const itemD = item ? douban(item) : {};
    const curRating = itemD.rating || "";
    const curSynopsis = itemD.synopsis || "";
    const doubanUrl = settingDoubanId ? ('https://movie.douban.com/subject/' + settingDoubanId + '/') : '';
    doubanSection = '<div class="settings-section"><div class="section-header"><h2>豆瓣关联</h2></div>'
      + '<p class="settings-hint">豆瓣目前无法自动爬取数据（WAF 屏蔽），请输入豆瓣 ID 后手动填写评分和剧情简介。</p>'
      + '<p class="settings-hint">豆瓣 ID 可在豆瓣网页 URL 中找到，如 <code>https://movie.douban.com/subject/<strong>10440076</strong>/</code></p>'
      + '<div class="settings-cat-row"><input id="doubanIdInput" style="flex:0.4" value="' + escapeHtml(settingDoubanId) + '" placeholder="豆瓣 ID"><input id="doubanRating" style="flex:0.15" value="' + escapeHtml(String(curRating)) + '" placeholder="评分"><button onclick="saveDoubanId()">保存</button>'
      + (doubanUrl ? '<button class="ghost" onclick="window.open(\'' + doubanUrl + '\')">打开豆瓣页</button>' : '')
      + '<button class="ghost" onclick="settingDoubanItemId=\'\';navigateTo({type:\'detail\', id:\'' + escapeJs(settingDoubanItemId) + '\'})">取消</button></div>'
      + '<div class="settings-cat-row" style="margin-top:6px"><textarea id="doubanSynopsis" style="flex:1;min-height:60px;padding:8px;border-radius:8px;background:rgba(255,255,255,.05);border:1px solid var(--line);color:var(--text);font-family:var(--font);font-size:13px;resize:vertical" placeholder="剧情简介（可选）">' + escapeHtml(curSynopsis) + '</textarea></div>'
      + '</div>';
  }

  app.innerHTML = '<section class="section">'
    + '<div class="section-header"><h2>设置</h2></div>'

    + doubanSection

    + '<div class="settings-section"><div class="section-header"><h2>目录分类</h2></div>'
    + '<p class="settings-hint">修改后点击保存将自动重新扫描。</p>'
    + '<div id="settingsCats">' + (rows || '<div class="empty">暂无分类</div>') + '</div>'
    + '<div class="settings-actions"><button onclick="addSettingsRow()">+ 添加分类</button></div></div>'

    + '<div class="settings-section"><div class="section-header"><h2>关于</h2></div>'
    + '<p class="settings-hint">MovieWall Desktop · 本地影视墙</p>'
    + '</div>'

    + '<div class="settings-actions"><button onclick="saveSettings()">保存并扫描</button><button class="ghost" onclick="goHome()">返回首页</button></div>'
    + '</section>';

  if (settingDoubanItemId) {
    const inp = document.getElementById("doubanIdInput");
    if (inp) setTimeout(() => inp.focus(), 100);
  }
}

function addSettingsRow() {
  const container = document.getElementById("settingsCats") || app.querySelector("#settingsCats");
  if (!container) return;
  const div = document.createElement("div");
  div.className = "settings-cat-row";
  div.innerHTML = '<input class="sc-folder" placeholder="文件夹名"><input class="sc-name" placeholder="显示名"><button class="ghost" onclick="this.closest(\'.settings-cat-row\').remove()">✕</button>';
  container.append(div);
}

async function saveSettings() {
  const rows = document.querySelectorAll("#settingsCats .settings-cat-row");
  const cats = {};
  for (const row of rows) {
    const folder = row.querySelector(".sc-folder").value.trim();
    const name = row.querySelector(".sc-name").value.trim();
    if (folder && name) cats[folder] = name;
  }
  const res = await fetch("/api/config", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({categories: cats})});
  const data = await res.json();
  if (data.ok) scanBtn.click();
}

async function loadLibrary() {
  showSkeleton();
  await fetchAllData();
  renderHome();
}

async function _pollProgress(bar) {
  return new Promise((resolve) => {
    const id = setInterval(async () => {
      try {
        const r = await fetch("/api/scan/progress");
        const p = await r.json();
        if (bar) {
          bar.style.transform = "scaleX(" + p.progress + ")";
          bar.title = p.message || "";
        }
        if (p.done) {
          clearInterval(id);
          resolve(p.error || null);
        }
      } catch (e) {
        clearInterval(id);
        resolve(null);
      }
    }, 500);
  });
}

async function _loadAfterScan() {
  MW.state.moreMenuOpen = null;
  MW.state.seasonMoreOpen = null;
  showSkeleton();
  const res = await fetch("/api/library");
  MW.state.library = await res.json();
  const s = MW.state.library.stats;
  const catCount = s.categories ? s.categories.length : 0;
  showToast("完成 - " + (s.movies + s.shows) + " 部 / " + s.episodes + " 集" + (catCount ? " · " + catCount + " 个分类" : ""));
  MW.state.navStack = [];
  renderHome();
}

scanBtn.onclick = async () => {
  const bar = document.getElementById("scanBar");
  const btn = scanBtn;
  btn.disabled = true;
  if (bar) { bar.classList.add("active"); bar.style.transform = "scaleX(0)"; }
  const res = await fetch("/api/scan", {method:"POST"});
  const data = await res.json();
  if (!data.ok) { showToast(data.error, 4000); btn.disabled = false; return; }
  const err = await _pollProgress(bar);
  btn.disabled = false;
  if (bar) bar.classList.remove("active");
  if (err) { showToast("扫描错误: " + err, 5000); }
  await _loadAfterScan();
};

async function updateMetadata() {
  const bar = document.getElementById("scanBar");
  const btn = document.getElementById("updateBtn");
  btn.disabled = true;
  if (bar) { bar.classList.add("active"); bar.style.transform = "scaleX(0)"; }
  showToast("开始更新元数据...");
  const res = await fetch("/api/update", {method:"POST"});
  const data = await res.json();
  if (!data.ok) { showToast(data.error, 4000); btn.disabled = false; return; }
  const err = await _pollProgress(bar);
  btn.disabled = false;
  if (bar) bar.classList.remove("active");
  if (err) { showToast("更新错误: " + err, 5000); }
  await _loadAfterScan();
}

/* ===== Single Item Update ===== */

async function updateSingleItem(mediaId, doubanId) {
  const bar = document.getElementById("scanBar");
  if (bar) { bar.classList.add("active"); bar.style.transform = "scaleX(0)"; }
  showToast("更新中...");
  const res = await fetch("/api/update_single", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({media_id: mediaId, douban_id: doubanId || ""})
  });
  const data = await res.json();
  if (bar) bar.classList.remove("active");
  if (data.ok) {
    showToast("已更新");
    MW.state.moreMenuOpen = null;
    MW.state.seasonMoreOpen = null;
    const libRes = await fetch("/api/library");
    MW.state.library = await libRes.json();
    renderRoute(MW.state.currentView);
  } else {
    showToast("更新失败: " + (data.error || "未知错误"), 3000);
  }
}

document.addEventListener("click", (e) => {
  if (MW.state.moreMenuOpen && !e.target.closest(".more-wrap") && !e.target.closest(".more-dropdown")) {
    MW.state.moreMenuOpen = null;
    renderRoute(MW.state.currentView);
  }
  if (MW.state.seasonMoreOpen && !e.target.closest(".season-more-wrap") && !e.target.closest(".season-more-dropdown")) {
    MW.state.seasonMoreOpen = null;
    renderRoute(MW.state.currentView);
  }
});

search.addEventListener("input", () => { MW.state.moreMenuOpen = null; MW.state.seasonMoreOpen = null; MW.state.navStack = []; renderHome(); });
window.addEventListener("keydown", e => { if (e.key === "Escape" && MW.state.currentView.type !== "home") goBackSmart(); });

// Mousewheel horizontal scroll for cast-scroll containers
document.addEventListener("wheel", (e) => {
  const scroll = e.target.closest(".cast-scroll");
  if (!scroll) return;
  if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
    e.preventDefault();
    scroll.scrollLeft += e.deltaY;
  }
}, { passive: false });

loadLibrary();
