let library = {items: [], stats: {}};
let activeCategory = "all";
let currentView = {type: "home"};
let navStack = [];
let players = [];
let categoriesConfig = {};
let expandedSeason = null;
let moreMenuOpen = null;

const app = document.querySelector("#app");
const search = document.querySelector("#search");
const typeFilter = document.querySelector("#typeFilter");
const scanBtn = document.querySelector("#scanBtn");
const breadcrumb = document.querySelector("#breadcrumb");

const ratingEditMode = {};
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
  delete ratingEditMode[itemId];
  renderRoute(currentView);
  apiPutRating(itemId, score);
  showToast("评分已保存 " + Number(score).toFixed(1) + " / 10");
}

function clearUserRating(itemId) {
  delete ratingsCache[itemId];
  delete ratingEditMode[itemId];
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

function imgOrPlaceholder(item, kind="poster", shape="poster", label="") {
  const src = artworkUrl(item, kind);
  const title = label || titleOf(item);
  const cls = shape ? "cover " + shape : "cover";
  const ph = item?.type === "episode" ? "placeholder episode-placeholder" : "placeholder";
  if (src) {
    return '<div class="' + cls + '"><img src="' + src + '" loading="lazy" onerror="this.parentElement.innerHTML=\'<div class=&quot;' + ph + '&quot;>' + escapeHtml(title) + '</div>\'"><div class="overlay-play">▶</div></div>';
  }
  return '<div class="' + cls + '"><div class="' + ph + '">' + escapeHtml(title) + '</div><div class="overlay-play">▶</div></div>';
}

/* ===== 星级评分 ===== */

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

/* ===== 高亮 ===== */

function highlightText(text, query) {
  if (!query) return escapeHtml(text);
  const escaped = escapeHtml(text);
  const q = escapeHtml(query).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return escaped.replace(new RegExp('(' + q + ')', 'gi'), '<mark>$1</mark>');
}

function metaBadges(item) {
  const t = tmdb(item), bits = [];
  if (item?.year) bits.push('<span class="badge">' + escapeHtml(item.year) + '</span>');
  if (t.rating) bits.push('<span class="badge hot">TMDB ' + Number(t.rating).toFixed(1) + '</span>');
  if (t.genres?.length) bits.push(...t.genres.slice(0, 3).map(g => '<span class="badge">' + escapeHtml(g) + '</span>'));
  if (item?.type === "show") bits.push('<span class="badge">' + (item.season_count || 0) + ' 季</span><span class="badge">' + (item.episode_count || 0) + ' 集</span>');
  return bits.join("");
}

/* ===== 面包屑 ===== */

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

/* ===== 路由 ===== */

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

/* ===== 首页 ===== */

function setCategory(key) {
  activeCategory = key;
  navStack = [];
  renderHome();
}

function getFilteredItems() {
  const q = search.value.trim().toLowerCase();
  const tf = typeFilter.value;
  return library.items.filter(item => {
    if (activeCategory !== "all" && item.category_key !== activeCategory) return false;
    if (tf !== "all" && item.type !== tf) return false;
    if (!q) return true;
    let bag = (titleOf(item) + " " + (item.title || "") + " " + (item.year || "") + " " + (item.category_name || "")).toLowerCase();
    if (item.type === "movie") bag += " " + (item.filename || "") + " " + (item.folder || "");
    if (item.type === "show") {
      for (const s of item.seasons || []) for (const ep of s.episodes || []) bag += " " + (s.title || "") + " " + (ep.title || "") + " " + (ep.filename || "");
    }
    return bag.includes(q);
  });
}

function renderHome() {
  currentView = {type:"home"};
  renderBreadcrumb();
  const items = getFilteredItems();
  if (!items.length) {
    app.innerHTML = '<section class="section"><div class="empty">暂无内容。请确认路径正确，然后点击"扫描"。</div></section>';
    return;
  }
  const hasQuery = search.value.trim().length > 0;
  const last = hasQuery ? null : getLastHistory();
  const continueCard = last ? renderContinueCard(last) : "";
  app.innerHTML = '<section class="section"><div class="home-grid">' + continueCard + items.map(renderHomeCard).join("") + '</div></section>';
}

function renderContinueCard(last) {
  const item = findItem(last.media_id);
  const title = last.show_title || last.title || titleOf(item);
  const label = last.label || last.short_label || "上次播放";
  const pb = renderPlayButtons(last.path, "{media_id:'" + last.media_id + "',type:'" + last.type + "',path:'" + escapeJs(last.path) + "',title:'" + escapeJs(title) + "',show_title:'" + escapeJs(last.show_title || title) + "',label:'" + escapeJs(label) + "',short_label:'" + escapeJs(last.short_label || "") + "'}").replace(/onclick="/g, 'onclick="event.stopPropagation();');
  return '<article class="card continue-inline-card" onclick="playSavedHistory()">' + imgOrPlaceholder(item || last, "poster", "poster", title) + '<div class="card-body"><div class="continue-kicker">继续观看</div><h4 class="card-title">' + escapeHtml(title) + '</h4><div class="meta">' + escapeHtml(label) + '</div><div class="mini-actions" onclick="event.stopPropagation()">' + pb + (item ? '<button class="ghost" onclick="openDetail(\'' + item.id + '\')">详情</button>' : "") + '</div></div></article>';
}

function renderHomeCard(item) {
  const q = search.value.trim();
  const hist = getItemHistory(item);
  const subtitle = item.type === "movie" ? (item.category_name || "") + (item.year ? " · " + item.year : "") : (item.category_name || "") + (item.year ? " · " + item.year : "") + " · " + (item.season_count || 0) + " 季 · " + (item.episode_count || 0) + " 集";
  return '<article class="card" onclick="openDetail(\'' + item.id + '\')">' + imgOrPlaceholder(item, "poster", "poster") + '<div class="card-body"><h4 class="card-title">' + highlightText(titleOf(item), q) + '</h4><div class="meta">' + escapeHtml(subtitle) + '</div><div class="rating-row">' + metaBadges(item) + '</div>' + (hist ? '<div class="progress-pill">上次播放到 ' + escapeHtml(hist.short_label || hist.label || "") + '</div>' : "") + '</div></article>';
}

function openDetail(id) { navigateTo({type:"detail", id}); }
function toggleSeason(showId, seasonNumber) {
  if (expandedSeason === showId + "|" + seasonNumber) { expandedSeason = null; renderRoute(currentView); return; }
  expandedSeason = showId + "|" + seasonNumber;
  renderRoute(currentView);
}

/* ===== 播放 ===== */

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

async function openFolder(folder) {
  await fetch("/api/open_folder", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({folder})});
}

function renderPlayButtons(path, entryStr) {
  if (!players || players.length <= 1) {
    return '<button onclick="playMedia(\'' + escapeJs(path) + '\',' + entryStr + ')">播放</button>';
  }
  return players.map(p => '<button onclick="playMedia(\'' + escapeJs(path) + '\',' + entryStr + ',\'' + escapeJs(p.name) + '\')">' + escapeHtml(p.name) + '</button>').join("");
}

/* ===== 更多菜单 ===== */

function toggleMore(id) { moreMenuOpen = moreMenuOpen === id ? null : id; renderRoute(currentView); }

function moreMenuHtml(item, actions) {
  const id = item.id;
  const open = moreMenuOpen === id;
  return '<div class="more-wrap"><button class="ghost more-btn" onclick="toggleMore(\'' + id + '\')">···</button>' + (open ? '<div class="more-dropdown" onclick="toggleMore(\'' + id + '\')">' + actions + '</div>' : '') + '</div>';
}

/* ===== 详情页 ===== */

function detailHero(item, bodyHtml) {
  const bg = backdropUrl(item);
  const poster = artworkUrl(item, "poster") || artworkUrl(item, "thumb");
  return '<section class="detail-hero">' + (bg ? '<div class="detail-backdrop" style="background-image:url(\'' + bg + '\')"></div>' : "") + '<div class="detail-overlay"></div><div class="detail-content"><div class="detail-poster">' + (poster ? '<img src="' + poster + '" loading="lazy">' : '<div class="placeholder">' + escapeHtml(titleOf(item)) + '</div>') + '</div><div class="detail-info">' + bodyHtml + '</div></div></section>';
}

function renderMovieDetail(item) {
  currentView = {type:"detail", id:item.id};
  renderBreadcrumb();
  const meta = tmdb(item);
  const overview = meta.overview;
  const origTitle = meta.original_title && meta.original_title !== titleOf(item) ? meta.original_title : "";
  const hist = getItemHistory(item);
  const entry = "{media_id:'" + item.id + "',type:'movie',path:'" + escapeJs(item.path) + "',title:'" + escapeJs(titleOf(item)) + "',show_title:'" + escapeJs(titleOf(item)) + "',label:'电影',short_label:'电影'}";
  const more = moreMenuHtml(item, '<button onclick="openFolder(\'' + escapeJs(item.folder) + '\')">打开文件夹</button>');
  const body = '<div class="rating-row">' + metaBadges(item) + '</div><h2>' + escapeHtml(titleOf(item)) + '</h2>' + (origTitle ? '<div class="detail-subtitle">' + escapeHtml(origTitle) + '</div>' : "") + (overview ? '<div class="overview-wrap"><div class="overview" id="overviewText">' + escapeHtml(overview) + '</div><button class="expand-btn" onclick="toggleOverview()">展开全部</button></div>' : "") + starRatingWidget(item) + '<div class="detail-actions">' + renderPlayButtons(item.path, entry) + more + '</div>';
  app.innerHTML = detailHero(item, body);
}

function renderShowDetail(item) {
  currentView = {type:"detail", id:item.id};
  renderBreadcrumb();
  const meta = tmdb(item);
  const overview = meta.overview;
  const origTitle = meta.original_title && meta.original_title !== titleOf(item) ? meta.original_title : "";
  const hist = getItemHistory(item);
  const more = moreMenuHtml(item, '<button onclick="openFolder(\'' + escapeJs(item.folder) + '\')">打开文件夹</button>');
  const body = '<div class="rating-row">' + metaBadges(item) + '</div><h2>' + escapeHtml(titleOf(item)) + '</h2>' + (origTitle ? '<div class="detail-subtitle">' + escapeHtml(origTitle) + '</div>' : "") + (overview ? '<div class="overview-wrap"><div class="overview" id="overviewText">' + escapeHtml(overview) + '</div><button class="expand-btn" onclick="toggleOverview()">展开全部</button></div>' : "") + starRatingWidget(item) + '<div class="detail-actions">' + (hist ? '<button onclick="playSavedHistory()" class="cta-btn">▶ 继续播放</button>' : "") + more + '</div>';
  const isExpanded = (snum) => expandedSeason === item.id + "|" + snum;
  app.innerHTML = detailHero(item, body) + '<section class="section"><div class="section-head"><h2>季</h2><small>' + (item.season_count || 0) + ' 季</small></div><div class="season-wall">' + (item.seasons || []).map(s => renderSeasonCard(item, s, isExpanded(s.season_number))).join("") + '</div>' + (item.seasons || []).filter(s => isExpanded(s.season_number)).map(s => renderInlineEpisodes(item, s)).join("") + '</section>';
}

function renderSeasonCard(show, season, expanded) {
  const hist = getItemHistory(show);
  const active = hist && Number(hist.season_number) === Number(season.season_number);
  const epHist = season.episodes.filter(ep => getItemHistory(show) && getItemHistory(show).episode_id === ep.id);
  const progress = hist && Number(hist.season_number) === Number(season.season_number) ? 1 : 0;
  const epWatched = season.episodes.filter(ep => historyCache[ep.id]).length;
  const progressPct = season.episode_count ? Math.round(epWatched / season.episode_count * 100) : 0;
  return '<article class="card season-card' + (expanded ? ' season-expanded' : '') + '" onclick="toggleSeason(\'' + show.id + '\',' + season.season_number + ')">' + imgOrPlaceholder(season,"poster","poster",titleOf(show) + " " + season.title) + '<div class="card-body"><h4 class="card-title">' + escapeHtml(season.title) + '</h4><div class="meta">' + (season.episode_count || 0) + ' 集</div>' + (progressPct > 0 ? '<div class="season-progress"><div class="season-progress-bar" style="width:' + progressPct + '%"></div></div>' : "") + '</div></article>';
}

function renderInlineEpisodes(show, season) {
  const firstEntry = episodeEntry(show, season, season.episodes[0], season.title + " · " + season.episodes[0].title);
  return '<div class="inline-episodes"><div class="inline-episodes-head">' + renderPlayButtons(season.episodes[0].path, firstEntry) + '</div><div class="episode-wall">' + (season.episodes || []).map(ep => renderEpisodeCard(show, season, ep)).join("") + '</div></div>';
}

/* ===== 季节详情（保留） ===== */

function renderSeasonDetail(show, season) {
  currentView = {type:"season", showId:show.id, seasonNumber:season.season_number};
  renderBreadcrumb();
  const firstEp = (season.episodes || [])[0];
  const firstEntry = firstEp ? episodeEntry(show, season, firstEp, season.title + " · " + firstEp.title) : "";
  const seasonHero = {...season, display_title:titleOf(show) + " · " + season.title, title:titleOf(show) + " · " + season.title, metadata:show.metadata};
  const overview = season?.metadata?.overview || tmdb(show).overview || "";
  const body = '<div class="rating-row">' + metaBadges(show) + '<span class="badge">' + (season.episode_count || 0) + ' 集</span></div><h2>' + escapeHtml(season.title) + '</h2>' + (overview ? '<div class="overview-wrap"><div class="overview" id="overviewText">' + escapeHtml(overview) + '</div><button class="expand-btn" onclick="toggleOverview()">展开全部</button></div>' : "") + starRatingWidget(season) + '<div class="detail-actions">' + (firstEp ? renderPlayButtons(firstEp.path, firstEntry) : '<button disabled>无剧集</button>') + '</div>';
  app.innerHTML = detailHero(seasonHero, body) + '<section class="section"><div class="episode-wall">' + (season.episodes || []).map(ep => renderEpisodeCard(show, season, ep)).join("") + '</div></section>';
}

/* ===== 剧集 ===== */

function episodeEntry(show, season, ep, label) {
  return "{media_id:'" + show.id + "',episode_id:'" + ep.id + "',type:'episode',path:'" + escapeJs(ep.path) + "',title:'" + escapeJs(ep.title) + "',show_title:'" + escapeJs(titleOf(show)) + "',season_number:" + season.season_number + ",episode_number:" + (ep.episode_number || 0) + ",label:'" + escapeJs(label) + "',short_label:'S" + String(season.season_number).padStart(2,"0") + "E" + String(ep.episode_number || 0).padStart(2,"0") + "'}";
}

function renderEpisodeCard(show, season, ep) {
  const hist = getItemHistory(show);
  const active = hist && hist.episode_id === ep.id;
  const label = season.title + " · " + ep.title;
  const entry = episodeEntry(show, season, ep, label);
  const pb = renderPlayButtons(ep.path, entry).replace(/onclick="/g, 'onclick="event.stopPropagation();');
  return '<article class="card episode-card' + (active ? ' active-episode' : '') + '" onclick="playMedia(\'' + escapeJs(ep.path) + '\',' + entry + ')">' + imgOrPlaceholder(ep,"thumb","",titleOf(show) + " " + label) + '<div class="card-body"><h4 class="card-title">' + escapeHtml(ep.title) + '</h4><div class="meta">' + escapeHtml(ep.filename) + '</div>' + (active ? '<div class="progress-pill">上次播放到这里</div>' : "") + '<div class="episode-actions" onclick="event.stopPropagation()">' + pb + '<button class="ghost" onclick="openFolder(\'' + escapeJs(ep.folder) + '\')">文件夹</button></div></div></article>';
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
  btn.textContent = expanded ? "收起" : "展开全部";
}

/* ===== 设置 ===== */

function renderSettings() {
  navStack = [];
  currentView = {type:"home"};
  renderBreadcrumb();
  const catKeys = Object.keys(categoriesConfig);
  const rows = catKeys.map((key, i) => '<div class="settings-cat-row"><input class="sc-folder" value="' + escapeHtml(key) + '" placeholder="文件夹名"><input class="sc-name" value="' + escapeHtml(categoriesConfig[key].name) + '" placeholder="显示名"><select class="sc-type"><option value="movie"' + (categoriesConfig[key].type === "movie" ? " selected" : "") + '>电影</option><option value="show"' + (categoriesConfig[key].type === "show" ? " selected" : "") + '>剧集</option></select><button class="ghost" onclick="this.closest(\'.settings-cat-row\').remove()">✕</button></div>').join("");
  app.innerHTML = '<section class="section"><div class="section-head"><h2>分类管理</h2></div><p class="settings-hint">修改后点击保存将自动重新扫描。</p><div id="settingsCats">' + (rows || '<div class="empty">暂无分类</div>') + '</div><div class="settings-actions"><button onclick="addSettingsRow()">+ 添加分类</button><button onclick="saveSettings()">保存</button><button class="ghost" onclick="goHome()">取消</button></div></section>';
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
  scanBtn.textContent = "扫描";
  scanBtn.disabled = true;
  if (bar) bar.classList.add("active");
  const res = await fetch("/api/scan", {method:"POST"});
  library = await res.json();
  scanBtn.disabled = false;
  scanBtn.textContent = "扫描";
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
typeFilter.addEventListener("change", () => { navStack = []; renderHome(); });
window.addEventListener("keydown", e => { if (e.key === "Escape" && currentView.type !== "home") goBackSmart(); });
loadLibrary();
