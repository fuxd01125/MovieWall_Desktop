let library = {items: [], stats: {}};
let activeCategory = "all";
let currentView = {type: "home"};
let navStack = [];

const app = document.querySelector("#app");
const tabs = document.querySelector("#tabs");
const search = document.querySelector("#search");
const scanBtn = document.querySelector("#scanBtn");

const ratingEditMode = {};

let ratingsCache = {};
let historyCache = {};

function loadHistory() { return historyCache; }
function loadRatings() { return ratingsCache; }

async function apiPutRating(mediaId, score) {
  await fetch("/api/ratings", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({media_id:mediaId, score})});
}
async function apiDeleteRating(mediaId) {
  await fetch(`/api/ratings/${mediaId}`, {method:"DELETE"});
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
}

function openRatingEditor(itemId) {
  ratingEditMode[itemId] = true;
  renderRoute(currentView);
}

function cancelRatingEditor(itemId) {
  delete ratingEditMode[itemId];
  renderRoute(currentView);
}

function clearUserRating(itemId) {
  delete ratingsCache[itemId];
  delete ratingEditMode[itemId];
  renderRoute(currentView);
  apiDeleteRating(itemId);
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
  if (item[kind]) return `/api/artwork/${item.id}/${kind}`;
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

function imgOrPlaceholder(item, kind="poster", shape="poster", label="") {
  const src = artworkUrl(item, kind);
  const title = label || titleOf(item);
  const cls = shape ? `cover ${shape}` : "cover";
  const ph = item?.type === "episode" ? "placeholder episode-placeholder" : "placeholder";
  if (src) {
    return `<div class="${cls}"><img src="${src}" onerror="this.parentElement.innerHTML='<div class=&quot;${ph}&quot;>${escapeHtml(title)}</div>'"><div class="overlay-play">▶</div></div>`;
  }
  return `<div class="${cls}"><div class="${ph}">${escapeHtml(title)}</div><div class="overlay-play">▶</div></div>`;
}

function ratingBadge(item) {
  const r = getUserRating(item);
  return r ? `<span class="badge mine">我的评分 ${Number(r.score).toFixed(1)}</span>` : "";
}

function ratingWidget(item) {
  const r = getUserRating(item);
  const current = r ? Number(r.score) : 0;
  const editing = !current || ratingEditMode[item.id];

  if (!editing) {
    return `<div class="user-rating-summary">
      <button class="my-rating-value" onclick="openRatingEditor('${item.id}')" title="点击修改评分">我的评分 ${current.toFixed(1)}</button>
      <button class="ghost rating-edit" onclick="openRatingEditor('${item.id}')">修改评分</button>
    </div>`;
  }

  let buttons = "";
  for (let i = 1; i <= 10; i++) {
    buttons += `<button class="rating-btn ${current === i ? "active" : ""}" title="评分 ${i}.0" onclick="setUserRating('${item.id}', ${i})">${current === i ? i.toFixed(1) : i}</button>`;
  }

  return `<div class="user-rating-panel">
    <div class="user-rating-head">
      <strong>我的评分</strong>
      <span>${current ? "当前 " + current.toFixed(1) : "未评分"}</span>
    </div>
    <div class="rating-buttons">${buttons}</div>
    <div class="rating-panel-actions">
      ${current ? `<button class="ghost rating-clear" onclick="clearUserRating('${item.id}')">清除评分</button>` : ""}
      ${current ? `<button class="ghost rating-cancel" onclick="cancelRatingEditor('${item.id}')">取消修改</button>` : ""}
    </div>
  </div>`;
}

function metaBadges(item) {
  const t = tmdb(item), d = douban(item), bits = [];
  // 卡片信息行只显示媒体信息，不混入“我的评分”。
  if (item?.year) bits.push(`<span class="badge">${escapeHtml(item.year)}</span>`);
  if (t.rating) bits.push(`<span class="badge hot">TMDB ${Number(t.rating).toFixed(1)}</span>`);
  if (d.rating) bits.push(`<span class="badge hot">豆瓣 ${escapeHtml(d.rating)}</span>`);
  if (t.genres?.length) bits.push(...t.genres.slice(0, 3).map(g => `<span class="badge">${escapeHtml(g)}</span>`));
  if (item?.type === "show") bits.push(`<span class="badge">${item.season_count || 0} 季</span><span class="badge">${item.episode_count || 0} 集</span>`);
  return bits.join("");
}

function navButtons(extra="") {
  return `<button class="ghost" onclick="goBackSmart()">返回</button><button class="ghost" onclick="goHome()">首页</button>${extra}`;
}

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
  renderRoute(view);
  window.scrollTo({top:0, behavior:"smooth"});
}

function goBackSmart() {
  const prev = navStack.pop();
  renderRoute(prev || {type:"home"});
  window.scrollTo({top:0, behavior:"smooth"});
}

function goHome() {
  navStack = [];
  renderHome();
  window.scrollTo({top:0, behavior:"smooth"});
}

function renderTabs() {
  const cats = library.stats?.categories || {};
  let html = `<div class="tab ${activeCategory === "all" ? "active" : ""}" onclick="setCategory('all')">全部 ${library.items.length}</div>`;
  for (const [key, info] of Object.entries(cats)) {
    html += `<div class="tab ${activeCategory === key ? "active" : ""}" onclick="setCategory('${escapeHtml(key)}')">${escapeHtml(info.name)} ${info.count}</div>`;
  }
  tabs.innerHTML = html;
}

function setCategory(key) {
  activeCategory = key;
  navStack = [];
  renderHome();
}

function getFilteredItems() {
  const q = search.value.trim().toLowerCase();
  return library.items.filter(item => {
    if (activeCategory !== "all" && item.category_key !== activeCategory) return false;
    if (!q) return true;
    let bag = `${titleOf(item)} ${item.title} ${item.year} ${item.category_name}`.toLowerCase();
    if (item.type === "movie") bag += ` ${item.filename} ${item.folder}`.toLowerCase();
    if (item.type === "show") {
      for (const s of item.seasons || []) for (const ep of s.episodes || []) bag += ` ${s.title} ${ep.title} ${ep.filename}`.toLowerCase();
    }
    return bag.includes(q);
  });
}

function renderHome() {
  currentView = {type:"home"};
  renderTabs();
  const items = getFilteredItems();
  if (!items.length) {
    app.innerHTML = `<section class="section"><div class="empty">暂无内容。请确认路径正确，然后点击“扫描”。</div></section>`;
    return;
  }
  const last = getLastHistory();
  const continueCard = last ? renderContinueCard(last) : "";
  if (activeCategory === "all") {
    app.innerHTML = `<section class="section"><div class="section-head"><h2>全部</h2><small>${items.length}${last ? " + 继续观看" : ""}</small></div><div class="home-strip">${continueCard}${items.map(renderHomeCard).join("")}</div></section>`;
  } else {
    const name = items[0]?.category_name || "分类";
    app.innerHTML = `<section class="section"><div class="section-head"><h2>${escapeHtml(name)}</h2><small>${items.length} 项</small></div><div class="home-grid">${items.map(renderHomeCard).join("")}</div></section>`;
  }
}

function renderContinueCard(last) {
  const item = findItem(last.media_id);
  const title = last.show_title || last.title || titleOf(item);
  const label = last.label || last.short_label || "上次播放";
  return `<article class="card continue-inline-card" onclick="playSavedHistory()">
    ${imgOrPlaceholder(item || last, "poster", "poster", title)}
    <div class="card-body"><div class="continue-kicker">继续观看</div><h4 class="card-title">${escapeHtml(title)}</h4><div class="meta">${escapeHtml(label)}</div><div class="progress-pill">上次播放到这里</div><div class="mini-actions" onclick="event.stopPropagation()"><button onclick="playSavedHistory()">播放</button>${item ? `<button class="ghost" onclick="openDetail('${item.id}')">详情</button>` : ""}</div></div>
  </article>`;
}

function renderHomeCard(item) {
  const hist = getItemHistory(item);
  const subtitle = item.type === "movie" ? `${item.category_name}${item.year ? " · " + item.year : ""}` : `${item.category_name}${item.year ? " · " + item.year : ""} · ${item.season_count || 0} 季 · ${item.episode_count || 0} 集`;
  return `<article class="card" onclick="openDetail('${item.id}')">${imgOrPlaceholder(item, "poster", "poster")}<div class="card-body"><h4 class="card-title">${escapeHtml(titleOf(item))}</h4><div class="meta">${escapeHtml(subtitle)}</div><div class="rating-row">${metaBadges(item)}</div>${hist ? `<div class="progress-pill">上次播放到 ${escapeHtml(hist.short_label || hist.label || "")}</div>` : ""}</div></article>`;
}

function openDetail(id) { navigateTo({type:"detail", id}); }
function openSeason(showId, seasonNumber) { navigateTo({type:"season", showId, seasonNumber}); }

async function playMedia(path, entry) {
  const route = {...currentView};
  const res = await fetch("/api/play", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({path})});
  const data = await res.json().catch(() => ({}));
  if (!data.ok) return alert(data.error || "播放失败");
  if (entry) {
    recordPlay(entry);
    renderRoute(route);
  }
}

function playSavedHistory() {
  const last = getLastHistory();
  if (last) playMedia(last.path, last);
}

async function openFolder(folder) {
  await fetch("/api/open_folder", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({folder})});
}

function detailHero(item, bodyHtml) {
  const bg = backdropUrl(item);
  const poster = artworkUrl(item, "poster") || artworkUrl(item, "thumb");
  return `<section class="detail-hero">${bg ? `<div class="detail-backdrop" style="background-image:url('${bg}')"></div>` : ""}<div class="detail-content"><div class="detail-poster">${poster ? `<img src="${poster}">` : `<div class="placeholder">${escapeHtml(titleOf(item))}</div>`}</div><div class="detail-info">${bodyHtml}</div></div></section>`;
}

function renderMovieDetail(item) {
  currentView = {type:"detail", id:item.id};
  renderTabs();
  const overview = tmdb(item).overview || item?.metadata?.local?.summary || "";
  const hist = getItemHistory(item);
  const body = `<div class="rating-row">${metaBadges(item)}</div><h2>${escapeHtml(titleOf(item))}</h2>${overview ? `<p class="overview">${escapeHtml(overview)}</p>` : ""}${hist ? `<div class="progress-pill">上次播放：${escapeHtml(hist.label || "这部电影")}</div>` : ""}${ratingWidget(item)}<div class="detail-actions"><button onclick="playMedia('${escapeJs(item.path)}',{media_id:'${item.id}',type:'movie',path:'${escapeJs(item.path)}',title:'${escapeJs(titleOf(item))}',show_title:'${escapeJs(titleOf(item))}',label:'电影',short_label:'电影'})">播放</button><button class="ghost" onclick="openFolder('${escapeJs(item.folder)}')">打开文件夹</button>${navButtons()}</div>`;
  app.innerHTML = detailHero(item, body);
}

function renderShowDetail(item) {
  currentView = {type:"detail", id:item.id};
  renderTabs();
  const overview = tmdb(item).overview || item?.metadata?.local?.summary || "";
  const hist = getItemHistory(item);
  const body = `<div class="rating-row">${metaBadges(item)}</div><h2>${escapeHtml(titleOf(item))}</h2>${overview ? `<p class="overview">${escapeHtml(overview)}</p>` : ""}${hist ? `<div class="progress-pill">上次播放到 ${escapeHtml(hist.label || "")}</div>` : ""}${ratingWidget(item)}<div class="detail-actions">${hist ? `<button onclick="playSavedHistory()">继续播放</button>` : ""}<button class="ghost" onclick="openFolder('${escapeJs(item.folder)}')">打开文件夹</button>${navButtons()}</div>`;
  app.innerHTML = `${detailHero(item, body)}<section class="section"><div class="section-head"><h2>季</h2><small>${item.season_count || 0} 季</small></div><div class="season-wall">${(item.seasons || []).map(s => renderSeasonCard(item, s)).join("")}</div></section>`;
}

function renderSeasonCard(show, season) {
  const hist = getItemHistory(show);
  const active = hist && Number(hist.season_number) === Number(season.season_number);
  return `<article class="card" onclick="openSeason('${show.id}',${season.season_number})">${imgOrPlaceholder(season,"poster","poster",`${titleOf(show)} ${season.title}`)}<div class="card-body"><h4 class="card-title">${escapeHtml(season.title)}</h4><div class="meta">${season.episode_count || 0} 集</div>${""}${active ? `<div class="progress-pill">上次看到本季</div>` : ""}</div></article>`;
}

function renderSeasonDetail(show, season) {

  currentView = {
    type:"season",
    showId:show.id,
    seasonNumber:season.season_number
  };

  renderTabs();

  const seasonHero = {
    ...season,
    display_title:`${titleOf(show)} · ${season.title}`,
    title:`${titleOf(show)} · ${season.title}`,
    metadata:show.metadata
  };

  // 季简介
  const overview =
    season?.metadata?.overview ||
    tmdb(show).overview ||
    show?.metadata?.local?.summary ||
    "";

  const body = `

    <div class="rating-row">
      ${metaBadges(show)}
      <span class="badge">${season.episode_count || 0} 集</span>
    </div>

    <h2>${escapeHtml(season.title)}</h2>

    ${
      overview
      ? `<p class="overview">${escapeHtml(overview)}</p>`
      : ""
    }

    ${ratingWidget(season)}

    <div class="detail-actions">

      <button onclick="playFirstEpisode('${show.id}',${season.season_number})">
        播放本季第一集
      </button>

      <button
        class="ghost"
        onclick="openFolder('${escapeJs(season.folder)}')">
        打开文件夹
      </button>

      ${navButtons(`
        <button
          class="ghost"
          onclick="renderRoute({type:'detail',id:'${show.id}'})">
          全部季
        </button>
      `)}

    </div>
  `;

  app.innerHTML = `
    ${detailHero(seasonHero, body)}

    <section class="section">

      <div class="section-head">
        <h2>分集</h2>
        <small>${season.episode_count || 0} 集</small>
      </div>

      <div class="episode-wall">
        ${(season.episodes || [])
          .map(ep => renderEpisodeCard(show, season, ep))
          .join("")}
      </div>

    </section>
  `;
}



function episodeEntry(show, season, ep, label) {
  return `{media_id:'${show.id}',episode_id:'${ep.id}',type:'episode',path:'${escapeJs(ep.path)}',title:'${escapeJs(ep.title)}',show_title:'${escapeJs(titleOf(show))}',season_number:${season.season_number},episode_number:${ep.episode_number || 0},label:'${escapeJs(label)}',short_label:'S${String(season.season_number).padStart(2,"0")}E${String(ep.episode_number || 0).padStart(2,"0")}'}`;
}

function renderEpisodeCard(show, season, ep) {
  const hist = getItemHistory(show);
  const active = hist && hist.episode_id === ep.id;
  const label = `${season.title} · ${ep.title}`;
  const entry = episodeEntry(show, season, ep, label);
  return `<article class="card episode-card" onclick="playMedia('${escapeJs(ep.path)}',${entry})">${imgOrPlaceholder(ep,"thumb","",`${titleOf(show)} ${label}`)}<div class="card-body"><h4 class="card-title">${escapeHtml(ep.title)}</h4><div class="meta">${escapeHtml(ep.filename)}</div>${active ? `<div class="progress-pill">上次播放到这里</div>` : ""}<div class="episode-actions"><button onclick="event.stopPropagation(); playMedia('${escapeJs(ep.path)}',${entry})">播放</button><button class="ghost" onclick="event.stopPropagation(); openFolder('${escapeJs(ep.folder)}')">文件夹</button></div></div></article>`;
}

function playFirstEpisode(showId, seasonNumber) {
  const show = findItem(showId);
  const season = (show?.seasons || []).find(s => Number(s.season_number) === Number(seasonNumber));
  const ep = season?.episodes?.[0];
  if (!show || !season || !ep) return;
  const label = `${season.title} · ${ep.title}`;
  playMedia(ep.path, {media_id:show.id, episode_id:ep.id, type:"episode", path:ep.path, title:ep.title, show_title:titleOf(show), season_number:season.season_number, episode_number:ep.episode_number || 0, label, short_label:`S${String(season.season_number).padStart(2,"0")}E${String(ep.episode_number || 0).padStart(2,"0")}`});
}

function toggleOverview() {
  const overview = document.getElementById("overviewText");
  const button = document.querySelector(".expand-button");

  overview.classList.toggle("expanded"); // 切换展开样式

  if (overview.classList.contains("expanded")) {
    button.textContent = "收起";
  } else {
    button.textContent = "展开";
  }
}

async function loadLibrary() {
  const [libRes, ratingsRes, historyRes] = await Promise.all([
    fetch("/api/library"),
    fetch("/api/ratings"),
    fetch("/api/history")
  ]);
  library = await libRes.json();
  ratingsCache = await ratingsRes.json();
  historyCache = await historyRes.json();
  renderHome();
}

scanBtn.onclick = async () => {
  scanBtn.textContent = "扫描中...";
  scanBtn.disabled = true;
  const res = await fetch("/api/scan", {method:"POST"});
  library = await res.json();
  scanBtn.disabled = false;
  scanBtn.textContent = "扫描";
  if (library.error) alert(library.error);
  navStack = [];
  renderHome();
};

search.addEventListener("input", () => { navStack = []; renderHome(); });
window.addEventListener("keydown", e => { if (e.key === "Escape" && currentView.type !== "home") goBackSmart(); });
loadLibrary();
