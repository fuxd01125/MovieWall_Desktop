let library = {items: [], stats: {}};
let activeCategory = "all";
let activeTab = "all";
let currentView = {type: "home"};
let navStack = [];
let players = [];
let categoriesConfig = {};
let expandedSeason = null;
let moreMenuOpen = null;
let seasonMoreOpen = null;

const app = document.querySelector("#app");
const search = document.querySelector("#search");
const catTabs = document.querySelector("#catTabs");
const scanBtn = document.querySelector("#scanBtn");
const breadcrumb = document.querySelector("#breadcrumb");

let ratingsCache = {};
let historyCache = {};
let favoritesCache = [];
let historyPollInterval = null;

function loadHistory() { return historyCache; }
function loadRatings() { return ratingsCache; }
function isFavorite(id) { return favoritesCache.includes(id); }

async function apiPutRating(mediaId, score) {
  await fetch("/api/ratings", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({media_id:mediaId, score})});
}
async function apiDeleteRating(mediaId) {
  await fetch("/api/ratings/" + mediaId, {method:"DELETE"});
}
async function apiPutHistory(entry) {
  await fetch("/api/history", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify(entry)});
}

async function apiToggleFavorite(mediaId) {
  const res = await fetch("/api/favorites", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({media_id: mediaId})});
  return await res.json();
}

function toggleFavorite(itemId) {
  const wasFav = isFavorite(itemId);
  if (wasFav) {
    favoritesCache = favoritesCache.filter(id => id !== itemId);
  } else {
    favoritesCache.push(itemId);
  }
  renderRoute(currentView);
  apiToggleFavorite(itemId);
  showToast(wasFav ? '已取消收藏' : '已收藏');
}

function recordPlay(entry) {
  // IMPORTANT: must use Unix seconds (same as backend time.time()) not ISO string.
  // SQLite ORDER BY sorts numbers vs text differently — using ISO string would
  // cause load_all_history() to always return this entry instead of the monitor's.
  const item = {...entry, played_at: Date.now() / 1000};
  historyCache[item.media_id] = item;
  historyCache.__last = item;
  apiPutHistory(item);
}

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
      const old = historyCache[mediaId];
      const oldTime = old ? _normalizeTime(old.played_at) : 0;
      const newTime = _normalizeTime(entry.played_at);
      if (!old || old.episode_id !== entry.episode_id || newTime > oldTime) {
        historyCache[mediaId] = entry;
        changed = true;
      }
    }
    // Recompute __last as the entry with the largest played_at
    let latest = null;
    let latestTime = 0;
    for (const mediaId of Object.keys(historyCache)) {
      if (mediaId === '__last') continue;
      const e = historyCache[mediaId];
      const t = _normalizeTime(e.played_at);
      if (t > latestTime) { latestTime = t; latest = e; }
    }
    if (latest) historyCache.__last = latest;
    if (changed) renderRoute(currentView);
  } catch (e) { /* ignore poll errors */ }
}

function startHistoryPolling() {
  if (historyPollInterval) return;
  historyPollInterval = setInterval(_pollHistory, 3000);
}

function stopHistoryPolling() {
  if (historyPollInterval) {
    clearInterval(historyPollInterval);
    historyPollInterval = null;
  }
}

function getLastHistory() { return historyCache.__last || null; }
function getItemHistory(item) { return item ? historyCache[item.id] : null; }
function getUserRating(item) { return item ? ratingsCache[item.id] || null : null; }

function setUserRating(itemId, score) {
  ratingsCache[itemId] = {score: Number(score), rated_at: new Date().toISOString()};
  renderRoute(currentView);
  apiPutRating(itemId, score);
  showToast("评分已保存 " + Number(score).toFixed(1) + " / 10");
}

function clearUserRating(itemId) {
  delete ratingsCache[itemId];
  renderRoute(currentView);
  apiDeleteRating(itemId);
  showToast("评分已清除");
}

function escapeHtml(s) {
  return String(s || "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");
}
function escapeJs(s) {
  return String(s || "").replaceAll("\\","\\\\").replaceAll("'","\\'").replaceAll("\n","\\n").replaceAll("\r","\\r");
}
function titleOf(item) { return item?.display_title || item?.title || item?.filename || "未命名"; }
function tmdb(item) { return item?.metadata?.tmdb || {}; }
function douban(item) { return item?.metadata?.douban || {}; }

function artworkUrl(item, kind="poster") {
  if (!item) return "";
  // Shows: TMDB poster takes priority over local file (which may be an episode screenshot)
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
  requestAnimationFrame(() => el.classList.add("show"));
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 300);
  }, duration || 2500);
}

/* ===== Category Tabs ===== */

function renderCategoryTabs() {
  const catStats = library.stats?.categories || [];
  const tabs = [
    {key:"all", label:"全部"},
    {key:"movie", label:"电影"},
    {key:"show", label:"剧集"},
    ...catStats.map(c => ({key:"cat:" + c.key, label: c.name}))
  ];
  catTabs.innerHTML = tabs.map(t =>
    '<button class="cat-tab' + (activeTab === t.key ? ' active' : '') + '" onclick="setTab(\'' + t.key + '\')">' + t.label + '</button>'
  ).join("");
}

function setTab(key) {
  moreMenuOpen = null;
  seasonMoreOpen = null;
  activeTab = key;
  navStack = [];
  renderHome();
}

/* ===== Highlight ===== */

function highlightText(text, query) {
  if (!query) return escapeHtml(text);
  const escaped = escapeHtml(text);
  const q = escapeHtml(query).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return escaped.replace(new RegExp('(' + q + ')', 'gi'), '<mark>$1</mark>');
}

/* ===== Rating Badge (unified) ===== */

function renderRatingBadge(score, opts) {
  if (score == null) return '';
  const num = Number(score);
  if (isNaN(num) || num <= 0) return '';
  const size = opts?.sm ? ' sm' : opts?.lg ? ' lg' : '';
  return '<span class="rating-badge' + size + '">★ ' + num.toFixed(1) + '</span>';
}

function renderDualRating(item) {
  const t = tmdb(item);
  const d = douban(item);
  const tRating = t.rating || "";
  const dRating = d.rating || "";
  const dCount = d.rating_count || "";
  let html = '';
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
  if (currentView.type === "detail" || currentView.type === "season") {
    const item = findItem(currentView.type === "detail" ? currentView.id : currentView.showId);
    if (item) {
      html += '<span class="bc-sep">/</span><span class="bc-item" onclick="goHome()">' + escapeHtml(item.category_name) + '</span>';
      html += '<span class="bc-sep">/</span><span class="bc-item bc-current">' + escapeHtml(titleOf(item)) + '</span>';
    }
  }
  if (currentView.type === "season") {
    const show = findItem(currentView.showId);
    const season = (show?.seasons || []).find(s => Number(s.season_number) === Number(currentView.seasonNumber));
    if (season) {
      html += '<span class="bc-sep">/</span><span class="bc-item bc-current">' + escapeHtml(season.title) + '</span>';
    }
  }
  breadcrumb.innerHTML = html;
}

/* ===== Routing ===== */

function findItem(id) { return library.items.find(i => i.id === id); }
function findEpisode(episodeId) {
  for (const show of library.items.filter(i => i.type === "show")) {
    for (const season of show.seasons || []) {
      for (const episode of season.episodes || []) {
        if (episode.id === episodeId) return {show, season, episode};
      }
    }
  }
  return null;
}

function renderRoute(view) {
  if (!view || view.type === "home") { moreMenuOpen = null; return renderHome(); }
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
}

function navigateTo(view) {
  moreMenuOpen = null;
  seasonMoreOpen = null;
  navStack.push({...currentView});
  expandedSeason = null;
  renderRoute(view);
  window.scrollTo({top:0, behavior:"smooth"});
}

function goBackSmart() {
  moreMenuOpen = null;
  seasonMoreOpen = null;
  const prev = navStack.pop();
  expandedSeason = null;
  renderRoute(prev || {type:"home"});
  window.scrollTo({top:0, behavior:"smooth"});
}

function goHome() {
  moreMenuOpen = null;
  seasonMoreOpen = null;
  navStack = [];
  expandedSeason = null;
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
  currentView = {type:"home"};
  renderCategoryTabs();
  renderBreadcrumb();

  if (!library.items.length) {
    app.innerHTML = '<section class="section"><div class="empty">暂无内容。请确认路径正确，然后点击"扫描"。</div></section>';
    return;
  }

  const items = getFilteredItems();
  if (!items.length) {
    app.innerHTML = '<section class="section"><div class="empty">没有匹配的内容。试试其他分类或搜索词。</div></section>';
    return;
  }

  const hasQuery = search.value.trim().length > 0;
  const continueItems = hasQuery ? [] : getContinueItems();

  // ── "全部" tab → Hero + Row layout ────────────
  if (activeTab === "all" && !hasQuery) {
    const heroItem = pickHeroItem(items, continueItems, hasQuery);

    const movies = items.filter(i => i.type === "movie");
    const shows = items.filter(i => i.type === "show");
    const catStats = library.stats?.categories || [];
    const recent = [...items].sort((a, b) => (b.updated_at || b.created_at || 0) - (a.updated_at || a.created_at || 0)).slice(0, 20);

    let html = renderHero(heroItem);

    if (continueItems.length > 0) {
      html += renderRowSection("继续观看", continueItems, renderContinueCard);
    }
    if (movies.length > 0) {
      html += renderRowSection("电影", movies, renderHomeCard, "movie");
    }
    if (shows.length > 0) {
      html += renderRowSection("剧集", shows, renderHomeCard, "show");
    }
    // Dynamic category sections — any category from config appears automatically
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

  // ── Non-all tab or search → grid layout ─────
  const gridMovies = items.filter(i => i.type === "movie");
  const gridShows = items.filter(i => i.type === "show");
  const gridOther = items.filter(i => i.type !== "movie" && i.type !== "show");
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
    if (gridMovies.length > 0) {
      html += '<section class="section">'
        + '<div class="section-header"><h2>电影</h2><small>' + gridMovies.length + ' 部</small></div>'
        + '<div class="grid">' + gridMovies.map(renderHomeCard).join('') + '</div></section>';
    }
    if (gridShows.length > 0) {
      html += '<section class="section">'
        + '<div class="section-header"><h2>剧集</h2><small>' + gridShows.length + ' 部</small></div>'
        + '<div class="grid">' + gridShows.map(renderHomeCard).join('') + '</div></section>';
    }
    if (gridOther.length > 0) {
      html += '<section class="section">'
        + '<div class="section-header"><h2>其他</h2></div>'
        + '<div class="grid">' + gridOther.map(renderHomeCard).join('') + '</div></section>';
    }
  }

  app.innerHTML = html;
}

function getFilteredItems() {
  const q = search.value.trim().toLowerCase();
  return library.items.filter(item => {
    if (activeTab === "movie") {
      if (item.type !== "movie") return false;
    } else if (activeTab === "show") {
      if (item.type !== "show") return false;
    } else if (activeTab.startsWith("cat:")) {
      const catKey = activeTab.slice(4);
      if (item.category_key !== catKey) return false;
    }
    // activeTab === "all" → no filter
    if (!q) return true;
    let bag = (titleOf(item) + " " + (item.title || "") + " " + (item.year || "") + " " + (item.category_name || "")).toLowerCase();
    if (item.type === "movie") bag += " " + (item.filename || "") + " " + (item.folder || "");
    if (item.type === "show") {
      for (const s of item.seasons || []) for (const ep of s.episodes || []) bag += " " + (s.title || "") + " " + (ep.title || "") + " " + (ep.filename || "");
    }
    return bag.includes(q);
  });
}

function getContinueItems() {
  const items = [];
  for (const [mediaId, hist] of Object.entries(historyCache)) {
    if (mediaId === "__last") continue;
    const item = findItem(mediaId);
    if (item) items.push({item, hist});
  }
  const q = search.value.trim().toLowerCase();
  return items.filter(({item}) => {
    if (activeTab === "movie") {
      if (item.type !== "movie") return false;
    } else if (activeTab === "show") {
      if (item.type !== "show") return false;
    } else if (activeTab.startsWith("cat:")) {
      const catKey = activeTab.slice(4);
      if (item.category_key !== catKey) return false;
    }
    if (!q) return true;
    const bag = (titleOf(item) + " " + (item.year || "")).toLowerCase();
    return bag.includes(q);
  }).sort((a, b) => new Date(b.hist.played_at||0) - new Date(a.hist.played_at||0));
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
  const t = tmdb(item);
  const d = douban(item);
  const genres = (t.genres || []).slice(0, 2);
  const hist = getItemHistory(item);
  const typeLabel = item.type === "show" ? ((item.season_count || 0) + " 季") : "电影";
  let metaHtml = '';
  if (item.year) metaHtml += '<span class="rating-badge sm">' + escapeHtml(item.year) + '</span>';
  if (d.rating) metaHtml += '<span class="rating-badge sm douban">豆 ' + Number(d.rating).toFixed(1) + '</span>';
  else if (t.rating) metaHtml += renderRatingBadge(t.rating, {sm:true});
  if (genres.length) metaHtml += genres.map(g => '<span class="rating-badge sm" style="background:rgba(255,255,255,.08);color:var(--muted);font-weight:500">' + escapeHtml(g) + '</span>').join('');
  return '<div class="card-overlay">'
    + '<div class="poster-actions">'
    + '<button class="poster-play" onclick="event.stopPropagation();' + primaryPlayAction(item) + '" title="播放">▶</button>'
    + '<button class="poster-info" onclick="event.stopPropagation();openDetail(\'' + item.id + '\')" title="详情">i</button>'
    + '</div>'
    + '<div class="card-meta">' + metaHtml + '</div>'
    + '<div class="card-overlay-title">' + escapeHtml(titleOf(item)) + '</div>'
    + '<div class="card-overlay-subtitle">' + (hist ? '继续观看' : escapeHtml(typeLabel)) + '</div>'
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
  let progressPct = 0;
  if (isShow) {
    const totalEps = item.episode_count || 0;
    const watchedEps = (item.seasons || []).reduce((sum, s) =>
      sum + (s.episodes || []).filter(ep => historyCache[ep.id]).length, 0);
    progressPct = totalEps ? Math.round(watchedEps / totalEps * 100) : 0;
  }
  const histEntry = "{media_id:'" + item.id + "',type:'" + item.type + "',path:'" + escapeJs(hist.path) + "',title:'" + escapeJs(title) + "',show_title:'" + escapeJs(hist.show_title || title) + "',label:'" + escapeJs(hist.label || "") + "',short_label:'" + escapeJs(hist.short_label || "") + "'}";
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
    + '<div class="poster-actions"><button class="poster-play" onclick="event.stopPropagation();playMedia(\'' + escapeJs(hist.path) + '\',' + histEntry + ')" title="继续播放">▶</button><button class="poster-info" onclick="event.stopPropagation();openDetail(\'' + item.id + '\')" title="详情">i</button></div>'
    + '<div class="card-meta"><span class="rating-badge sm">' + escapeHtml(label) + '</span></div>'
    + '<div class="card-overlay-title">' + escapeHtml(title) + '</div>'
    + '<div class="card-overlay-subtitle">继续观看</div>'
    + '</div>'
    + (progressPct > 0 ? '<div class="card-progress"><div class="card-progress-bar" style="width:' + progressPct + '%"></div></div>' : '')
    + '</div>'
    + '<div class="card-body"><div class="continue-kicker">▶ 继续观看</div><h4 class="card-title">' + escapeHtml(title) + '</h4></div>'
    + '</article>';
}

/* ===== Home Render ===== */

function showSkeleton() {
  const card = '<div class="skeleton-card"><div class="skeleton-poster skeleton"></div><div class="skeleton-title skeleton"></div></div>';
  app.innerHTML = '<section class="section loading-section"><div class="grid">' + card.repeat(12) + '</div></section>';
}

function openDetail(id) { navigateTo({type:"detail", id}); }
function toggleSeason(showId, seasonNumber) {
  if (expandedSeason === showId + "|" + seasonNumber) { expandedSeason = null; renderRoute(currentView); return; }
  expandedSeason = showId + "|" + seasonNumber;
  renderRoute(currentView);
  requestAnimationFrame(() => {
    const el = document.querySelector('.season-expanded-wrap');
    if (el) el.scrollIntoView({behavior:"smooth", block:"start"});
  });
}

/* ===== Playback ===== */

async function playMedia(path, entry, player) {
  const route = {...currentView};
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

function playSavedHistory() {
  const last = getLastHistory();
  if (last) playMedia(last.path, last);
}

function playItemHistory(itemId) {
  const hist = historyCache[itemId];
  if (hist) playMedia(hist.path, hist);
}

async function openFolder(folder) {
  await fetch("/api/open_folder", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({folder})});
}

function renderPlayButtons(path, entryStr) {
  return '<button onclick="playMedia(\'' + escapeJs(path) + '\',' + entryStr + ')">▶ 播放</button>';
}

/* ===== More Menu ===== */

function toggleMore(id, e) { if (e) e.stopPropagation(); moreMenuOpen = moreMenuOpen === id ? null : id; renderRoute(currentView); }
function toggleSeasonMore(showId, sn, e) {
  if (e) e.stopPropagation();
  const id = "smore-" + showId + "-" + sn;
  seasonMoreOpen = seasonMoreOpen === id ? null : id;
  renderRoute(currentView);
}

function moreMenuHtml(item, extraActions) {
  const id = item.id;
  const open = moreMenuOpen === id;
  let actions = '';
  if (players && players.length > 1) {
    actions += players.map(p => '<button onclick="playMedia(\'' + escapeJs(item.path) + '\',{media_id:\'' + item.id + '\'},\'' + escapeJs(p.name) + '\')">用 ' + escapeHtml(p.name) + ' 播放</button>').join("");
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
  if (!abstract && !abstract_2) return '';
  let tags = [];
  if (abstract) {
    abstract.split(' / ').forEach(part => {
      part = part.trim();
      if (!part) return;
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
  }
  html += '</div>';
  return html;
}

function detailHero(item, bodyHtml) {
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
    + '<button class="back-hero-btn" onclick="event.stopPropagation();goBackSmart()" title="返回" aria-label="返回">'
    + '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>'
    + '</button>'
    + '<div class="detail-content">'
    + '<div class="detail-poster">'
    + (poster ? '<img src="' + poster + '" loading="lazy">' : '<div class="placeholder">' + escapeHtml(titleOf(item)) + '</div>')
    + '</div>'
    + '<div class="detail-info">' + bodyHtml + '</div>'
    + '</div></section>';
}

function renderMovieDetail(item) {
  currentView = {type:"detail", id:item.id};
  renderCategoryTabs();
  renderBreadcrumb();
  const meta = tmdb(item);
  const overview = meta.overview;
  const origTitle = meta.original_title && meta.original_title !== titleOf(item) ? meta.original_title : "";
  const hist = getItemHistory(item);
  const entry = "{media_id:'" + item.id + "',type:'movie',path:'" + escapeJs(item.path) + "',title:'" + escapeJs(titleOf(item)) + "',show_title:'" + escapeJs(titleOf(item)) + "',label:'电影',short_label:'电影'}";
  const d = douban(item);
  const more = moreMenuHtml(item, '<button onclick="openFolder(\'' + escapeJs(item.folder) + '\')">打开文件夹</button><button onclick="updateSingleItem(\'' + item.id + '\')">更新此项目</button><button onclick="openDoubanSetting(\'' + item.id + '\',\'' + escapeJs(d.douban_id || "") + '\')">' + (d.douban_id ? '修改豆瓣ID' : '设置豆瓣ID') + '</button>');

  const body = '<h1>' + escapeHtml(titleOf(item)) + '</h1>'
    + (origTitle ? '<div class="detail-subtitle">' + escapeHtml(origTitle) + '</div>' : '')
    + '<div class="detail-primary-meta">' + renderPrimaryMeta(item) + '</div>'
    + '<div class="genre-tags">' + renderGenreTags(item) + '</div>'
    + renderDoubanTags(item)
    + (overview ? '<div class="overview-wrap"><div class="overview full">' + escapeHtml(overview) + '</div></div>' : '')
    + starRatingWidget(item)
    + '<div class="detail-actions">'
    + (hist ? '<button class="cta-btn" onclick="event.stopPropagation();playItemHistory(\'' + item.id + '\')">▶ 继续播放</button>' : '<button class="cta-btn" onclick="event.stopPropagation();playMedia(\'' + escapeJs(item.path) + '\',' + entry + ')">▶ 播放</button>')
    + more
    + '</div>';

  app.innerHTML = detailHero(item, body);
}

function renderShowDetail(item) {
  currentView = {type:"detail", id:item.id};
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

  const body = '<h1>' + escapeHtml(titleOf(item)) + '</h1>'
    + (origTitle ? '<div class="detail-subtitle">' + escapeHtml(origTitle) + '</div>' : '')
    + '<div class="detail-primary-meta">' + renderPrimaryMeta(item) + '</div>'
    + '<div class="genre-tags">' + renderGenreTags(item) + '</div>'
    + renderDoubanTags(item)
    + (overview ? '<div class="overview-wrap"><div class="overview full">' + escapeHtml(overview) + '</div></div>' : '')
    + starRatingWidget(item)
    + '<div class="detail-actions">'
    + (hist ? '<button class="cta-btn" onclick="event.stopPropagation();playItemHistory(\'' + item.id + '\')">▶ 继续播放</button>' : '')
    + (firstEntry ? '<button class="cta-btn" onclick="event.stopPropagation();playMedia(\'' + escapeJs(firstEp.ep.path) + '\',' + firstEntry + ')">▶ 播放第1集</button>' : '')
    + '<button class="cta-btn secondary' + (isFavorite(item.id) ? ' favorited' : '') + '" onclick="event.stopPropagation();toggleFavorite(\'' + item.id + '\')">' + (isFavorite(item.id) ? '♥' : '♡') + ' 收藏</button>'
    + more
    + '</div>';

  const isExpanded = (snum) => expandedSeason === item.id + "|" + snum;
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
  app.innerHTML = detailHero(item, body) + seasonHtml;
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
  const epWatched = season.episodes.filter(ep => historyCache[ep.id]).length;
  const progressPct = season.episode_count ? Math.round(epWatched / season.episode_count * 100) : 0;
  const t = tmdb(show);
  const sm = show._season_meta || {};
  const sMeta = sm[String(season.season_number)] || {};
  const tmdbSeasonData = (t._season_data || {})[String(season.season_number)] || {};
  const seasonYear = sMeta.air_date ? sMeta.air_date.toString().slice(0,4) : season.year || show.year || "";
  const seasonPoster = tmdbSeasonData.poster_url || sMeta.poster_url || artworkUrl(season, "poster") || "";
  const moreId = "smore-" + show.id + "-" + season.season_number;
  const showMore = seasonMoreOpen === moreId;
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
  const t = tmdb(show);
  const sm = show._season_meta || {};
  const sMeta = sm[String(season.season_number)] || {};
  const tmdbSeasonData = (t._season_data || {})[String(season.season_number)] || {};
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
  currentView = {type:"season", showId:show.id, seasonNumber:season.season_number};
  renderCategoryTabs();
  renderBreadcrumb();

  const firstEp = (season.episodes || [])[0];
  const firstEntry = firstEp ? episodeEntry(show, season, firstEp, season.title + " · " + firstEp.title) : "";
  const t = tmdb(show);
  const sm = show._season_meta || {};
  const sMeta = sm[String(season.season_number)] || {};
  const tmdbSeasonData = (t._season_data || {})[String(season.season_number)] || {};
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
    + (seasonSynopsis ? '<div class="overview-wrap"><div class="overview full">' + escapeHtml(seasonSynopsis) + '</div></div>' : '')
    + starRatingWidget(show)
    + '<div class="detail-actions">'
    + (hist ? '<button class="cta-btn" onclick="event.stopPropagation();playItemHistory(\'' + show.id + '\')">▶ 继续播放</button>' : '')
    + (firstEp ? '<button class="cta-btn" onclick="playMedia(\'' + escapeJs(firstEp.path) + '\',' + firstEntry + ')">▶ 播放第1集</button>' : '<button class="cta-btn" disabled>无剧集</button>')
    + '<button class="cta-btn secondary' + (isFavorite(show.id) ? ' favorited' : '') + '" onclick="event.stopPropagation();toggleFavorite(\'' + show.id + '\')">' + (isFavorite(show.id) ? '♥' : '♡') + ' 收藏</button>'
    + '<button class="cta-btn secondary" onclick="event.stopPropagation();navigateTo({type:\'detail\', id:\'' + show.id + '\'})">← 返回剧集</button>'
    + more
    + '</div>';

  app.innerHTML = detailHero(seasonHero, body)
    + '<section class="section">'
    + '<div class="section-header"><h2>剧集</h2><small>' + (season.episode_count || 0) + ' 集</small></div>'
    + '<div class="episode-list">'
    + (season.episodes || []).map(ep => renderEpisodeCard(show, season, ep)).join("")
    + '</div></section>';
}

function renderSeasonDoubanTags(show, season) {
  const sm = (show._season_meta || {});
  const sMeta = sm[String(season.season_number)] || {};
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
  const epHist = historyCache[ep.id];
  const thumbSrc = artworkUrl(ep, "thumb") || artworkUrl(ep, "poster");
  const epNum = "S" + String(season.season_number).padStart(2,"0") + "E" + String(ep.episode_number || 0).padStart(2,"0");

  return '<div class="episode-row' + (active ? ' active-episode' : '') + '" onclick="playMedia(\'' + escapeJs(ep.path) + '\',' + entry + ')">'
    + '<div class="episode-row-thumb">'
    + (thumbSrc
      ? '<img src="' + thumbSrc + '" loading="lazy" onerror="this.parentElement.innerHTML=\'<div class=\\\'placeholder episode-placeholder\\\'>' + escapeHtml(epNum) + '</div>\'">'
      : '<div class="placeholder episode-placeholder">' + escapeHtml(epNum) + '</div>')
    + '<div class="play-badge"><span>▶</span></div>'
    + '</div>'

    + '<div class="episode-row-body">'
    + '<div class="episode-row-top">'
    + '<span class="episode-row-num' + (active ? ' active-num' : '') + '">' + epNum + '</span>'
    + '<span class="episode-row-title">' + escapeHtml(ep.title || ep.filename) + '</span>'
    + '</div>'
    + '<div class="episode-row-overview">' + escapeHtml(ep.overview || ep.filename || "") + '</div>'
    + (epHist ? '<div class="episode-row-progress"><div class="bar" style="width:100%"></div></div>' : '')
    + '</div>'

    + '<div class="episode-row-play"><button onclick="event.stopPropagation();playMedia(\'' + escapeJs(ep.path) + '\',' + entry + ')" title="播放">▶</button></div>'
    + '</div>';
}

function playFirstEpisode(showId, seasonNumber) {
  const show = findItem(showId);
  const season = (show?.seasons || []).find(s => Number(s.season_number) === Number(seasonNumber));
  const ep = season?.episodes?.[0];
  if (!show || !season || !ep) return;
  const label = season.title + " · " + ep.title;
  playMedia(ep.path, {media_id:show.id, episode_id:ep.id, season_id:season.id, type:"episode", path:ep.path, title:ep.title, show_title:titleOf(show), season_number:season.season_number, episode_number:ep.episode_number || 0, label, short_label:"S" + String(season.season_number).padStart(2,"0") + "E" + String(ep.episode_number || 0).padStart(2,"0")});
}

/* ===== Settings ===== */

let settingDoubanId = "";
let settingDoubanItemId = "";

function openDoubanSetting(itemId, currentDoubanId) {
  moreMenuOpen = null;
  seasonMoreOpen = null;
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
  library = await libRes.json();
  navigateTo({type:"detail", id: itemId});
}

async function saveDoubanIdAndUpdate() {
  const id = settingDoubanId.trim();
  const itemId = settingDoubanItemId;
  if (!itemId) return;
  settingDoubanItemId = "";
  settingDoubanId = "";
  await updateSingleItem(itemId, id);
}

async function clearDoubanId(itemId) {
  await fetch("/api/metadata/douban/" + itemId, {method:"DELETE"});
  showToast("已清除豆瓣关联");
  const libRes = await fetch("/api/library");
  library = await libRes.json();
  navigateTo({type:"detail", id: itemId});
}

function renderSettings() {
  stopHistoryPolling();
  navStack = [];
  renderCategoryTabs();
  renderBreadcrumb();
  const catKeys = Object.keys(categoriesConfig);
  const rows = catKeys.map((key, i) => '<div class="settings-cat-row"><input class="sc-folder" value="' + escapeHtml(key) + '" placeholder="文件夹名"><input class="sc-name" value="' + escapeHtml(categoriesConfig[key].name) + '" placeholder="显示名"><button class="ghost" onclick="this.closest(\'.settings-cat-row\').remove()">✕</button></div>').join("");

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
  const [libRes, ratingsRes, historyRes, playersRes, configRes, favRes] = await Promise.all([
    fetch("/api/library"), fetch("/api/ratings"), fetch("/api/history"),
    fetch("/api/players"), fetch("/api/config"), fetch("/api/favorites")
  ]);
  library = await libRes.json();
  ratingsCache = await ratingsRes.json();
  historyCache = await historyRes.json();
  players = await playersRes.json();
  categoriesConfig = (await configRes.json()).categories || {};
  normalizeCategoriesConfig();
  favoritesCache = await favRes.json();
  renderHome();
}

function normalizeCategoriesConfig() {
  const normalized = {};
  for (const [key, value] of Object.entries(categoriesConfig || {})) {
    if (typeof value === "string") {
      normalized[key] = {name: value};
    } else {
      normalized[key] = {name: value?.name || key};
    }
  }
  categoriesConfig = normalized;
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
  moreMenuOpen = null;
  seasonMoreOpen = null;
  showSkeleton();
  const res = await fetch("/api/library");
  library = await res.json();
  const s = library.stats;
  const catCount = s.categories ? s.categories.length : 0;
  showToast("完成 - " + (s.movies + s.shows) + " 部 / " + s.episodes + " 集" + (catCount ? " · " + catCount + " 个分类" : ""));
  navStack = [];
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
    moreMenuOpen = null;
    seasonMoreOpen = null;
    const libRes = await fetch("/api/library");
    library = await libRes.json();
    renderRoute(currentView);
  } else {
    showToast("更新失败: " + (data.error || "未知错误"), 3000);
  }
}

document.addEventListener("click", (e) => {
  if (moreMenuOpen && !e.target.closest(".more-wrap") && !e.target.closest(".more-dropdown")) {
    moreMenuOpen = null;
    renderRoute(currentView);
  }
  if (seasonMoreOpen && !e.target.closest(".season-more-wrap") && !e.target.closest(".season-more-dropdown")) {
    seasonMoreOpen = null;
    renderRoute(currentView);
  }
});

search.addEventListener("input", () => { moreMenuOpen = null; seasonMoreOpen = null; navStack = []; renderHome(); });
window.addEventListener("keydown", e => { if (e.key === "Escape" && currentView.type !== "home") goBackSmart(); });
loadLibrary();
