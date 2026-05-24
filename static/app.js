let library = {items: [], stats: {}};
let activeCategory = "all";
let activeTab = "all";
let currentView = {type: "home"};
let navStack = [];
let players = [];
let categoriesConfig = {};
let expandedSeason = null;
let moreMenuOpen = null;

const app = document.querySelector("#app");
const search = document.querySelector("#search");
const catTabs = document.querySelector("#catTabs");
const scanBtn = document.querySelector("#scanBtn");
const breadcrumb = document.querySelector("#breadcrumb");

let ratingsCache = {};
let historyCache = {};

function loadHistory() { return historyCache; }
function loadRatings() { return ratingsCache; }

async function apiPutRating(mediaId, score) {
  await fetch("/api/ratings", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({media_id:mediaId, score})});
}
async function apiDeleteRating(mediaId) {
  await fetch("/api/ratings/" + mediaId, {method:"DELETE"});
}
async function apiPutHistory(entry) {
  await fetch("/api/history", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify(entry)});
}

function recordPlay(entry) {
  const item = {...entry, played_at: new Date().toISOString()};
  historyCache[item.media_id] = item;
  historyCache.__last = item;
  apiPutHistory(item);
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

function artworkUrl(item, kind="poster") {
  if (!item) return "";
  if (item[kind]) return "/api/artwork/" + item.id + "/" + kind;
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
  const tabs = [
    {key:"all", label:"全部"},
    {key:"movie", label:"电影"},
    {key:"show", label:"剧集"},
    {key:"anime", label:"动漫"}
  ];
  catTabs.innerHTML = tabs.map(t =>
    '<button class="cat-tab' + (activeTab === t.key ? ' active' : '') + '" onclick="setTab(\'' + t.key + '\')">' + t.label + '</button>'
  ).join("");
}

function setTab(key) {
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

/* ===== Star Rating (user input) ===== */

function starRatingWidget(item) {
  const r = getUserRating(item);
  const current = r ? Number(r.score) : 0;
  const fullStars = Math.floor(current / 2);
  const halfStar = (current % 2) >= 1 ? 1 : 0;
  let stars = "";
  for (let i = 1; i <= 5; i++) {
    if (i <= fullStars) stars += '<span class="star star-full" onclick="setUserRating(\'' + item.id + '\',' + (i * 2) + ')">★</span>';
    else if (i === fullStars + 1 && halfStar) stars += '<span class="star star-half" onclick="setUserRating(\'' + item.id + '\',' + (i * 2) + ')">★</span>';
    else stars += '<span class="star star-empty" onclick="setUserRating(\'' + item.id + '\',' + (i * 2) + ')">☆</span>';
  }
  const label = current ? '<span class="star-score">' + current.toFixed(1) + '</span>' : '<span class="star-hint">评分</span>';
  return '<div class="star-rating">' + stars + label + (current ? '<button class="star-clear" onclick="clearUserRating(\'' + item.id + '\')" title="清除评分">✕</button>' : '') + '</div>';
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
  moreMenuOpen = null;
  if (!view || view.type === "home") return renderHome();
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
  navStack.push({...currentView});
  expandedSeason = null;
  renderRoute(view);
  window.scrollTo({top:0, behavior:"smooth"});
}

function goBackSmart() {
  const prev = navStack.pop();
  expandedSeason = null;
  renderRoute(prev || {type:"home"});
  window.scrollTo({top:0, behavior:"smooth"});
}

function goHome() {
  navStack = [];
  expandedSeason = null;
  renderHome();
  window.scrollTo({top:0, behavior:"smooth"});
}

/* ===== Home ===== */

function getFilteredItems() {
  const q = search.value.trim().toLowerCase();
  return library.items.filter(item => {
    if (activeTab === "anime") {
      const ck = (item.category_key || "").toLowerCase();
      const cn = (item.category_name || "").toLowerCase();
      if (!ck.includes("anime") && !cn.includes("anime") && !ck.includes("动漫") && !cn.includes("动漫") && !ck.includes("动画") && !cn.includes("动画")) return false;
    } else if (activeTab !== "all") {
      if (item.type !== activeTab) return false;
    }
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
    if (activeTab === "anime") {
      const ck = (item.category_key || "").toLowerCase();
      const cn = (item.category_name || "").toLowerCase();
      if (!ck.includes("anime") && !cn.includes("anime") && !ck.includes("动漫") && !cn.includes("动漫") && !ck.includes("动画") && !cn.includes("动画")) return false;
    } else if (activeTab !== "all") {
      if (item.type !== activeTab) return false;
    }
    if (!q) return true;
    const bag = (titleOf(item) + " " + (item.year || "")).toLowerCase();
    return bag.includes(q);
  }).sort((a, b) => new Date(b.hist.played_at||0) - new Date(a.hist.played_at||0));
}

/* ===== Card Overlay ===== */

function renderCardOverlay(item) {
  const t = tmdb(item);
  const genres = (t.genres || []).slice(0, 2);
  let metaHtml = '';
  if (item.year) metaHtml += '<span class="rating-badge sm">' + escapeHtml(item.year) + '</span>';
  if (t.rating) metaHtml += renderRatingBadge(t.rating, {sm:true});
  if (genres.length) metaHtml += genres.map(g => '<span class="rating-badge sm" style="background:rgba(255,255,255,.08);color:var(--muted);font-weight:500">' + escapeHtml(g) + '</span>').join('');
  return '<div class="card-overlay"><div class="card-meta">' + metaHtml + '</div><div class="card-play-btn" onclick="event.stopPropagation();openDetail(\'' + item.id + '\')">▶ 详情</div></div>';
}

function renderHomeCard(item) {
  const q = search.value.trim();
  return '<article class="card" onclick="openDetail(\'' + item.id + '\')">'
    + '<div class="card-poster">'
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
  return '<article class="card" onclick="playMedia(\'' + escapeJs(hist.path) + '\',' + histEntry + ')">'
    + '<div class="card-poster">'
    + (artworkUrl(item, "poster")
      ? '<img src="' + artworkUrl(item, "poster") + '" loading="lazy" onerror="this.parentElement.innerHTML=\'<div class=\\\'placeholder\\\'>' + escapeHtml(title) + '</div>\'">'
      : '<div class="placeholder">' + escapeHtml(title) + '</div>')
    + '<div class="card-overlay"><div class="card-meta"><span class="rating-badge sm">' + escapeHtml(label) + '</span></div><div class="card-play-btn" onclick="event.stopPropagation();playMedia(\'' + escapeJs(hist.path) + '\',' + histEntry + ')">▶ 播放</div></div>'
    + (progressPct > 0 ? '<div class="card-progress"><div class="card-progress-bar" style="width:' + progressPct + '%"></div></div>' : '')
    + '</div>'
    + '<div class="card-body"><div class="continue-kicker">▶ 继续观看</div><h4 class="card-title">' + escapeHtml(title) + '</h4></div>'
    + '</article>';
}

/* ===== Home Render ===== */

function showSkeleton() {
  const card = '<div class="skeleton-card"><div class="skeleton-poster skeleton"></div><div class="skeleton-title skeleton"></div></div>';
  app.innerHTML = '<section class="section"><div class="grid">' + card.repeat(12) + '</div></section>';
}

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
  let html = '';

  if (continueItems.length > 0) {
    html += '<section class="section">'
      + '<div class="section-header"><h2>继续观看</h2><small>' + continueItems.length + ' 项</small></div>'
      + '<div class="continue-strip">'
      + continueItems.map(renderContinueCard).join('')
      + '</div></section>';
  }

  const movies = items.filter(i => i.type === "movie");
  const shows = items.filter(i => i.type === "show");
  const other = items.filter(i => i.type !== "movie" && i.type !== "show");

  if (hasQuery) {
    html += '<section class="section">'
      + '<div class="section-header"><h2>搜索结果</h2><small>' + items.length + ' 项</small></div>'
      + '<div class="grid">' + items.map(renderHomeCard).join('') + '</div></section>';
  } else {
    if (continueItems.length > 0 && movies.length > 0) {
      html += '<section class="section">'
        + '<div class="section-header"><h2>电影</h2></div>'
        + '<div class="grid">' + movies.map(renderHomeCard).join('') + '</div></section>';
    } else if (movies.length > 0) {
      html += '<section class="section">'
        + '<div class="section-header"><h2>电影</h2><small>' + movies.length + ' 部</small></div>'
        + '<div class="grid">' + movies.map(renderHomeCard).join('') + '</div></section>';
    }
    if (shows.length > 0) {
      html += '<section class="section">'
        + '<div class="section-header"><h2>剧集</h2><small>' + shows.length + ' 部</small></div>'
        + '<div class="grid">' + shows.map(renderHomeCard).join('') + '</div></section>';
    }
    if (other.length > 0) {
      html += '<section class="section">'
        + '<div class="section-header"><h2>其他</h2></div>'
        + '<div class="grid">' + other.map(renderHomeCard).join('') + '</div></section>';
    }
  }

  app.innerHTML = html;
}

function openDetail(id) { navigateTo({type:"detail", id}); }
function toggleSeason(showId, seasonNumber) {
  if (expandedSeason === showId + "|" + seasonNumber) { expandedSeason = null; renderRoute(currentView); return; }
  expandedSeason = showId + "|" + seasonNumber;
  const el = document.querySelector('.season-card.season-expanded');
  if (el) el.scrollIntoView({behavior:"smooth", block:"nearest"});
  renderRoute(currentView);
}

/* ===== Playback ===== */

async function playMedia(path, entry, player) {
  const route = {...currentView};
  const body = {path};
  if (player) body.player = player;
  const res = await fetch("/api/play", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
  const data = await res.json().catch(() => ({}));
  if (!data.ok) return alert(data.error || "播放失败");
  if (entry) { recordPlay(entry); renderRoute(route); }
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

function toggleMore(id) { moreMenuOpen = moreMenuOpen === id ? null : id; renderRoute(currentView); }

function moreMenuHtml(item, extraActions) {
  const id = item.id;
  const open = moreMenuOpen === id;
  let actions = '';
  if (players && players.length > 1) {
    actions += players.map(p => '<button onclick="playMedia(\'' + escapeJs(item.path) + '\',{media_id:\'' + item.id + '\'},\'' + escapeJs(p.name) + '\')">用 ' + escapeHtml(p.name) + ' 播放</button>').join("");
  }
  if (extraActions) actions += extraActions;
  return '<div class="more-wrap"><button class="ghost more-btn" onclick="toggleMore(\'' + id + '\')">···</button>' + (open ? '<div class="more-dropdown" onclick="toggleMore(\'' + id + '\')">' + actions + '</div>' : '') + '</div>';
}

/* ===== Detail Page ===== */

function renderGenreTags(item) {
  const t = tmdb(item);
  const genres = t.genres || [];
  return genres.map(g => '<span class="genre-tag">' + escapeHtml(g) + '</span>').join('');
}

function renderPrimaryMeta(item) {
  const t = tmdb(item);
  const parts = [];
  if (item.year) parts.push('<span class="year">' + escapeHtml(item.year) + '</span>');
  if (t.rating) parts.push(renderRatingBadge(t.rating));
  return parts.join('<span class="sep">·</span>');
}

function detailHero(item, bodyHtml) {
  const bg = backdropUrl(item);
  const poster = artworkUrl(item, "poster") || artworkUrl(item, "thumb");
  return '<section class="detail-hero">'
    + (bg ? '<div class="detail-backdrop" style="background-image:url(\'' + bg + '\')"></div>' : '')
    + '<div class="detail-overlay"></div>'
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
  const more = moreMenuHtml(item, '<button onclick="openFolder(\'' + escapeJs(item.folder) + '\')">打开文件夹</button>');

  const body = '<h1>' + escapeHtml(titleOf(item)) + '</h1>'
    + (origTitle ? '<div class="detail-subtitle">' + escapeHtml(origTitle) + '</div>' : '')
    + '<div class="detail-primary-meta">' + renderPrimaryMeta(item) + '</div>'
    + '<div class="genre-tags">' + renderGenreTags(item) + '</div>'
    + (overview ? '<div class="overview-wrap"><div class="overview" id="overviewText">' + escapeHtml(overview) + '</div><button class="expand-btn" onclick="toggleOverview()">展开</button></div>' : '')
    + starRatingWidget(item)
    + '<div class="detail-actions">'
    + (hist ? '<button class="cta-btn" onclick="event.stopPropagation();playItemHistory(\'' + item.id + '\')">▶ 继续播放</button>' : '<button class="cta-btn" onclick="event.stopPropagation();playMedia(\'' + escapeJs(item.path) + '\',' + entry + ')">▶ 播放</button>')
    + '<button class="cta-btn secondary" onclick="showToast(\'收藏功能开发中\')">☆ 收藏</button>'
    + '<button class="cta-btn secondary" onclick="showToast(\'评论功能开发中\')">✎ 写评论</button>'
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
  const more = moreMenuHtml(item, '<button onclick="openFolder(\'' + escapeJs(item.folder) + '\')">打开文件夹</button>');
  const firstEp = findFirstEpisode(item);
  const firstEntry = firstEp ? episodeEntry(item, firstEp.season, firstEp.ep, firstEp.season.title + " · " + firstEp.ep.title) : "";

  const body = '<h1>' + escapeHtml(titleOf(item)) + '</h1>'
    + (origTitle ? '<div class="detail-subtitle">' + escapeHtml(origTitle) + '</div>' : '')
    + '<div class="detail-primary-meta">' + renderPrimaryMeta(item) + '</div>'
    + '<div class="genre-tags">' + renderGenreTags(item) + '</div>'
    + (overview ? '<div class="overview-wrap"><div class="overview" id="overviewText">' + escapeHtml(overview) + '</div><button class="expand-btn" onclick="toggleOverview()">展开</button></div>' : '')
    + starRatingWidget(item)
    + '<div class="detail-actions">'
    + (hist ? '<button class="cta-btn" onclick="event.stopPropagation();playItemHistory(\'' + item.id + '\')">▶ 继续播放</button>' : '')
    + (firstEntry ? '<button class="cta-btn" onclick="event.stopPropagation();playMedia(\'' + escapeJs(firstEp.ep.path) + '\',' + firstEntry + ')">▶ 播放第1集</button>' : '')
    + '<button class="cta-btn secondary" onclick="showToast(\'收藏功能开发中\')">☆ 收藏</button>'
    + more
    + '</div>';

  const isExpanded = (snum) => expandedSeason === item.id + "|" + snum;
  app.innerHTML = detailHero(item, body)
    + '<section class="section">'
    + '<div class="section-header"><h2>季</h2><small>' + (item.season_count || 0) + ' 季</small></div>'
    + '<div class="season-wall">'
    + (item.seasons || []).map(s => renderSeasonCard(item, s, isExpanded(s.season_number))).join("")
    + '</div>'
    + (item.seasons || []).filter(s => isExpanded(s.season_number)).map(s => renderInlineEpisodes(item, s)).join("")
    + '</section>';
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
  const seasonMeta = season.metadata?.tmdb || {};
  const seasonRating = seasonMeta.vote_average || t.vote_average || "";
  const seasonYear = seasonMeta.air_date ? seasonMeta.air_date.slice(0,4) : season.year || show.year || "";
  return '<article class="card season-card' + (expanded ? ' season-expanded' : '') + '" onclick="toggleSeason(\'' + show.id + '\',' + season.season_number + ')">'
    + '<div class="card-poster">'
    + (artworkUrl(season, "poster")
      ? '<img src="' + artworkUrl(season, "poster") + '" loading="lazy">'
      : '<div class="placeholder">' + escapeHtml(titleOf(show)) + '</div>')
    + '</div>'
    + '<div class="card-body"><h4 class="card-title">' + escapeHtml(season.title) + '</h4>'
    + '<div class="season-meta">'
    + (seasonYear ? '<span class="year">' + seasonYear + '</span>' : '')
    + (season.episode_count ? '<span>' + season.episode_count + ' 集</span>' : '')
    + (seasonRating ? renderRatingBadge(seasonRating, {sm:true}) : '')
    + '</div>'
    + (progressPct > 0
      ? '<div class="season-progress"><div class="season-progress-bar" style="width:' + progressPct + '%"></div></div><div class="season-progress-text">已看 ' + epWatched + '/' + (season.episode_count || 0) + '</div>'
      : '')
    + '</div></article>';
}

function renderInlineEpisodes(show, season) {
  return '<div class="inline-episodes">'
    + '<div class="inline-episodes-head">' + escapeHtml(season.title) + ' · 剧集列表</div>'
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
  const seasonHero = {...season, display_title:titleOf(show) + " · " + season.title, title:titleOf(show) + " · " + season.title, metadata:show.metadata};
  const overview = season?.metadata?.overview || tmdb(show).overview || "";

  const body = '<h1>' + escapeHtml(season.title) + '</h1>'
    + '<div class="detail-primary-meta">' + renderPrimaryMeta(show) + '</div>'
    + '<div class="genre-tags">' + renderGenreTags(show) + '</div>'
    + (overview ? '<div class="overview-wrap"><div class="overview" id="overviewText">' + escapeHtml(overview) + '</div><button class="expand-btn" onclick="toggleOverview()">展开</button></div>' : '')
    + '<div class="detail-actions">'
    + (firstEp ? '<button class="cta-btn" onclick="playMedia(\'' + escapeJs(firstEp.path) + '\',' + firstEntry + ')">▶ 播放第1集</button>' : '<button class="cta-btn" disabled>无剧集</button>')
    + '</div>';

  app.innerHTML = detailHero(seasonHero, body)
    + '<section class="section">'
    + '<div class="section-header"><h2>剧集</h2><small>' + (season.episode_count || 0) + ' 集</small></div>'
    + '<div class="episode-list">'
    + (season.episodes || []).map(ep => renderEpisodeCard(show, season, ep)).join("")
    + '</div></section>';
}

/* ===== Episode Entry ===== */

function episodeEntry(show, season, ep, label) {
  return "{media_id:'" + show.id + "',episode_id:'" + ep.id + "',type:'episode',path:'" + escapeJs(ep.path) + "',title:'" + escapeJs(ep.title) + "',show_title:'" + escapeJs(titleOf(show)) + "',season_number:" + season.season_number + ",episode_number:" + (ep.episode_number || 0) + ",label:'" + escapeJs(label) + "',short_label:'S" + String(season.season_number).padStart(2,"0") + "E" + String(ep.episode_number || 0).padStart(2,"0") + "'}";
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
  playMedia(ep.path, {media_id:show.id, episode_id:ep.id, type:"episode", path:ep.path, title:ep.title, show_title:titleOf(show), season_number:season.season_number, episode_number:ep.episode_number || 0, label, short_label:"S" + String(season.season_number).padStart(2,"0") + "E" + String(ep.episode_number || 0).padStart(2,"0")});
}

function toggleOverview() {
  const wrap = document.querySelector(".overview");
  const btn = document.querySelector(".expand-btn");
  if (!wrap || !btn) return;
  const expanded = wrap.classList.toggle("expanded");
  btn.textContent = expanded ? "收起" : "展开";
}

/* ===== Settings ===== */

function renderSettings() {
  navStack = [];
  currentView = {type:"home"};
  renderCategoryTabs();
  renderBreadcrumb();
  const catKeys = Object.keys(categoriesConfig);
  const rows = catKeys.map((key, i) => '<div class="settings-cat-row"><input class="sc-folder" value="' + escapeHtml(key) + '" placeholder="文件夹名"><input class="sc-name" value="' + escapeHtml(categoriesConfig[key].name) + '" placeholder="显示名"><select class="sc-type"><option value="movie"' + (categoriesConfig[key].type === "movie" ? " selected" : "") + '>电影</option><option value="show"' + (categoriesConfig[key].type === "show" ? " selected" : "") + '>剧集</option></select><button class="ghost" onclick="this.closest(\'.settings-cat-row\').remove()">✕</button></div>').join("");
  app.innerHTML = '<section class="section"><div class="section-header"><h2>分类管理</h2></div><p class="settings-hint">修改后点击保存将自动重新扫描。</p><div id="settingsCats">' + (rows || '<div class="empty">暂无分类</div>') + '</div><div class="settings-actions"><button onclick="addSettingsRow()">+ 添加分类</button><button onclick="saveSettings()">保存</button><button class="ghost" onclick="goHome()">取消</button></div></section>';
}

function addSettingsRow() {
  const container = document.getElementById("settingsCats") || app.querySelector("#settingsCats");
  if (!container) return;
  const div = document.createElement("div");
  div.className = "settings-cat-row";
  div.innerHTML = '<input class="sc-folder" placeholder="文件夹名"><input class="sc-name" placeholder="显示名"><select class="sc-type"><option value="movie">电影</option><option value="show" selected>剧集</option></select><button class="ghost" onclick="this.closest(\'.settings-cat-row\').remove()">✕</button>';
  container.append(div);
}

async function saveSettings() {
  const rows = document.querySelectorAll("#settingsCats .settings-cat-row");
  const cats = {};
  for (const row of rows) {
    const folder = row.querySelector(".sc-folder").value.trim();
    const name = row.querySelector(".sc-name").value.trim();
    const type = row.querySelector(".sc-type").value;
    if (folder && name) cats[folder] = {name, type};
  }
  const res = await fetch("/api/config", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({categories: cats})});
  const data = await res.json();
  if (data.ok) scanBtn.click();
}

async function loadLibrary() {
  showSkeleton();
  const [libRes, ratingsRes, historyRes, playersRes, configRes] = await Promise.all([
    fetch("/api/library"), fetch("/api/ratings"), fetch("/api/history"),
    fetch("/api/players"), fetch("/api/config")
  ]);
  library = await libRes.json();
  ratingsCache = await ratingsRes.json();
  historyCache = await historyRes.json();
  players = await playersRes.json();
  categoriesConfig = (await configRes.json()).categories || {};
  renderHome();
}

scanBtn.onclick = async () => {
  const bar = document.getElementById("scanBar");
  scanBtn.disabled = true;
  if (bar) bar.classList.add("active");
  showSkeleton();
  const res = await fetch("/api/scan", {method:"POST"});
  library = await res.json();
  scanBtn.disabled = false;
  if (bar) bar.classList.remove("active");
  if (library.error) { showToast(library.error, 4000); return; }
  const s = library.stats;
  showToast("扫描完成 - " + (s.movies + s.shows) + " 部作品 / " + s.episodes + " 集");
  navStack = [];
  renderHome();
};

document.addEventListener("click", (e) => {
  if (moreMenuOpen && !e.target.closest(".more-wrap")) { moreMenuOpen = null; renderRoute(currentView); }
});

search.addEventListener("input", () => { navStack = []; renderHome(); });
window.addEventListener("keydown", e => { if (e.key === "Escape" && currentView.type !== "home") goBackSmart(); });
loadLibrary();
