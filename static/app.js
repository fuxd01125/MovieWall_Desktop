/* ============================================================
   MovieWall — Main Application
   Routing, rendering, and user interaction
   Depends on: mw-utils.js, mw-api.js, mw-state.js,
               mw-detail.js, mw-cards.js, mw-person.js, mw-settings.js
   ============================================================ */

/* ===== MW Module Aliases ===== */
const { escapeHtml, escapeJs, titleOf, tmdb, douban, seasonTmdb, seasonDouban, creditsCast, artworkUrl, backdropUrl, showToast, highlightText, renderDualRating } = MW.util;
const { apiPutRating, apiDeleteRating, apiPutHistory, apiToggleFavorite, openFolder, recordPlay } = MW.api;
const { findItem, isFavorite, getUserRating, getItemHistory, getLastHistory, getFilteredItems, getFilteredSortedItems, getContinueItems, normalizeCategoriesConfig, fetchAllData, setSort, getSortLabel, SORT_MODES } = MW.state;
const { pickHeroItem, renderHero, renderRowSection, renderCardOverlay, renderHomeCard, renderContinueCard, showSkeleton } = MW.cards;
const { renderGenreTags, renderPrimaryMeta, renderDoubanTags, detailHero, findFirstEpisode, renderSeasonCard, renderInlineEpisodes, renderSeasonDoubanTags, episodeEntry, renderEpisodeCard } = MW.detail;
const { renderCastSection, renderPersonDetail } = MW.person;
const { openDoubanSetting, saveDoubanId, renderSettings } = MW.settings;

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
  const tabs = [
    {key:"all", label:"首页"},
    ...catStats.map(c => ({key:"cat:" + c.key, label: c.name})),
    {key:"favorites", label:"收藏"}
  ];
  const tabsHtml = tabs.map(t =>
    '<button class="cat-tab' + (MW.state.activeTab === t.key ? ' active' : '') + '" onclick="setTab(\'' + t.key + '\')">' + t.label + '</button>'
  ).join("");
  const sortLabel = getSortLabel(MW.state.currentSort);
  const sortActive = MW.state.currentSort !== "default";
  const sortBtn = '<div class="sort-wrap">'
    + '<button class="sort-btn cat-tab' + (sortActive ? ' sort-active' : '') + '" onclick="event.stopPropagation();toggleSortMenu()">↕ ' + escapeHtml(sortLabel) + '</button>'
    + (MW.state.sortMenuOpen ? renderSortDropdown() : '')
    + '</div>';
  catTabs.innerHTML = tabsHtml + sortBtn;
}

function renderSortDropdown() {
  var html = '<div class="sort-dropdown">';
  for (var i = 0; i < SORT_MODES.length; i++) {
    var m = SORT_MODES[i];
    var cls = m.key === MW.state.currentSort ? ' class="active"' : '';
    html += '<button' + cls + ' onclick="event.stopPropagation();setSortMode(\'' + m.key + '\')">' + m.label + '</button>';
  }
  return html + '</div>';
}

function toggleSortMenu() {
  MW.state.sortMenuOpen = !MW.state.sortMenuOpen;
  renderRoute(MW.state.currentView);
}

function setSortMode(key) {
  setSort(key);
  renderRoute(MW.state.currentView);
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
  MW.state.activeTab = "all";
  search.value = "";
  renderRoute({type:"home"});
  window.scrollTo({top:0, behavior:"smooth"});
}

/* ===== Home ===== */

/* ── Home Page ──────────────────────────────────── */

function renderHome() {
  MW.state.currentView = {type:"home"};
  renderCategoryTabs();
  renderBreadcrumb();

  if (!MW.state.library.items.length) {
    app.innerHTML = '<section class="section"><div class="empty">暂无内容。请确认路径正确，然后点击"扫描"。</div></section>';
    return;
  }

  const items = getFilteredSortedItems();
  if (!items.length) {
    const emptyMsg = MW.state.activeTab === "favorites" ? "暂无收藏内容" : "没有匹配的内容。试试其他分类或搜索词。";
    app.innerHTML = '<section class="section"><div class="empty">' + emptyMsg + '</div></section>';
    return;
  }

  const hasQuery = search.value.trim().length > 0;
  const continueItems = hasQuery ? [] : getContinueItems();

  // ── "首页" tab → Hero + dynamic category row layout ────
  if (MW.state.activeTab === "all" && !hasQuery) {
    const heroItem = pickHeroItem(items, continueItems, hasQuery);

    const catStats = MW.state.library.stats?.categories || [];
    const recent = [...items].sort((a, b) => (b.updated_at || b.created_at || 0) - (a.updated_at || a.created_at || 0)).slice(0, 20);

    let html = renderHero(heroItem);

    if (continueItems.length > 0) {
      html += renderRowSection("继续观看", continueItems, renderContinueCard);
    }
    // Favorites row (sorted)
    const favItems = MW.state.sortItems(items.filter(i => MW.state.favoritesCache.includes(i.id)));
    if (favItems.length > 0) {
      html += renderRowSection("收藏", favItems, renderHomeCard, "favorites");
    }
    // Dynamic category sections (sorted within each row)
    for (const cat of catStats) {
      const catItems = MW.state.sortItems(items.filter(i => i.category_key === cat.key));
      if (catItems.length > 0) {
        html += renderRowSection(cat.name, catItems, renderHomeCard, "cat:" + cat.key);
      }
    }
    // Only show "最近添加" row when sort is default (avoid redundancy)
    if (MW.state.currentSort === "default" && recent.length > 0) {
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

/* ===== Home Render ===== */

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

function detailMenuActions(item, season) {
  var dd = douban(item);
  var t = tmdb(item);
  var folder = season ? (season.folder || item.folder) : item.folder;
  var deleteLabel = season ? '删除此季' : '删除此影视剧';
  var deleteTitle = season ? (titleOf(item) + ' ' + season.title) : titleOf(item);
  var deleteScope = season ? 'season' : 'show';
  var seasonNum = season ? season.season_number : '';
  // TMDB URL
  var tmdbUrl = '';
  if (t.tmdb_id) {
    if (season) {
      tmdbUrl = 'https://www.themoviedb.org/tv/' + t.tmdb_id + '/season/' + season.season_number;
    } else if (item.type === 'movie') {
      tmdbUrl = 'https://www.themoviedb.org/movie/' + t.tmdb_id;
    } else {
      tmdbUrl = 'https://www.themoviedb.org/tv/' + t.tmdb_id;
    }
  }
  return '<button onclick="openFolder(\'' + escapeJs(folder) + '\')">打开文件夹</button>'
    + '<button onclick="updateSingleItem(\'' + item.id + '\')">更新元数据</button>'
    + '<button onclick="openDoubanSetting(\'' + item.id + '\',\'' + escapeJs(dd.douban_id || "") + '\')">' + (dd.douban_id ? '修改豆瓣ID' : '设置豆瓣ID') + '</button>'
    + (tmdbUrl ? '<button onclick="window.open(\'' + tmdbUrl + '\')">在 TMDB 查看</button>' : '')
    + '<button class="danger-action" onclick="confirmDeleteMedia(\'' + item.id + '\',\'' + escapeJs(deleteTitle) + '\',\'' + deleteScope + '\',' + seasonNum + ')">' + deleteLabel + '</button>';
}

function confirmDeleteMedia(mediaId, title, scope, seasonNumber) {
  scope = scope || 'show';
  var msg = scope === 'season'
    ? '确认删除《' + title + '》？\n\n此操作只会删除该季目录，且不可恢复。'
    : '确认删除《' + title + '》？\n\n此操作会删除本地文件，且不可恢复。';
  if (!confirm(msg)) return;
  deleteMedia(mediaId, scope, seasonNumber);
}

async function deleteMedia(mediaId, scope, seasonNumber) {
  showToast("删除中...");
  MW.state.moreMenuOpen = null;
  try {
    var body = {media_id: mediaId, scope: scope || 'show'};
    if (scope === 'season' && seasonNumber !== undefined) body.season_number = seasonNumber;
    var res = await fetch("/api/delete_media", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)
    });
    var data = await res.json();
    if (data.ok) {
      showToast("已删除");
      var libRes = await fetch("/api/library");
      MW.state.library = await libRes.json();
      goHome();
    } else {
      showToast("删除失败: " + (data.error || "未知错误"), 4000);
    }
  } catch(e) {
    showToast("删除失败: 网络错误", 4000);
  }
}

/* ===== Detail Page ===== */

function renderMovieDetail(item) {
  MW.state.currentView = {type:"detail", id:item.id};
  renderCategoryTabs();
  renderBreadcrumb();
  const meta = tmdb(item);
  const overview = meta.overview;
  const origTitle = meta.original_title && meta.original_title !== titleOf(item) ? meta.original_title : "";
  const hist = getItemHistory(item);
  const entry = "{media_id:'" + item.id + "',type:'movie',path:'" + escapeJs(item.path) + "',title:'" + escapeJs(titleOf(item)) + "',show_title:'" + escapeJs(titleOf(item)) + "',label:'电影',short_label:'电影'}";
  const cast = (item.metadata?.credits?.cast || []).filter(c => c.person?.id);
  const more = moreMenuHtml(item, detailMenuActions(item));

  const body = '<h1>' + escapeHtml(titleOf(item)) + '</h1>'
    + (origTitle ? '<div class="detail-subtitle">' + escapeHtml(origTitle) + '</div>' : '')
    + '<div class="detail-primary-meta">' + renderPrimaryMeta(item) + '</div>'
    + '<div class="genre-tags">' + renderGenreTags(item) + '</div>'
    + renderDoubanTags(item)
    + (overview ? '<div class="overview">' + escapeHtml(overview) + '</div>' : '')
    + starRatingWidget(item)
    + '<div class="detail-actions">'
    + (hist ? '<button class="cta-btn" onclick="event.stopPropagation();playItemHistory(\'' + item.id + '\')">▶ 继续播放</button>' : '<button class="cta-btn" onclick="event.stopPropagation();playMedia(\'' + escapeJs(item.path) + '\',' + entry + ')">▶ 播放</button>')
    + '<button class="cta-btn secondary' + (isFavorite(item.id) ? ' favorited' : '') + '" onclick="event.stopPropagation();toggleFavorite(\'' + item.id + '\')">' + (isFavorite(item.id) ? '♥' : '♡') + ' 收藏</button>'
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
  const more = moreMenuHtml(item, detailMenuActions(item));
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
  const more = moreMenuHtml(show, detailMenuActions(show, season));

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
  if (MW.state.sortMenuOpen && !e.target.closest(".sort-wrap")) {
    MW.state.sortMenuOpen = false;
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
