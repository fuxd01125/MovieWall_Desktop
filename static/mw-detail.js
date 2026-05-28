/* ============================================================
   MovieWall — Detail Page Rendering
   Detail hero, season cards, episode cards, metadata sections
   Depends on: mw-utils.js, mw-state.js
   ============================================================ */

window.MW = window.MW || {};

(function() {
  "use strict";

  var util = MW.util;
  var state = MW.state;

  function renderGenreTags(item) {
    var t = util.tmdb(item);
    var genres = t.genres || [];
    return genres.map(function(g) { return '<span class="genre-tag">' + util.escapeHtml(g) + '</span>'; }).join('');
  }

  function renderPrimaryMeta(item) {
    var parts = [];
    if (item.year) parts.push('<span class="year">' + util.escapeHtml(item.year) + '</span>');
    var dualHtml = util.renderDualRating(item);
    if (dualHtml) parts.push(dualHtml);
    if (item.type === "show") {
      parts.push('<span class="year">' + (item.season_count || 0) + ' 季 · ' + (item.episode_count || 0) + ' 集</span>');
    }
    return parts.join('<span class="sep">·</span>');
  }

  function renderDoubanTags(item) {
    var d = util.douban(item);
    var abstract = d.abstract || "";
    var abstract_2 = d.abstract_2 || "";
    var cast = util.creditsCast(item);
    if (!abstract && !abstract_2 && !cast.length) return '';
    var t = util.tmdb(item);
    var existingGenres = (t.genres || []).map(function(g) { return g.toLowerCase(); });
    var tags = [];
    if (abstract) {
      abstract.split(' / ').forEach(function(part) {
        part = part.trim();
        if (!part) return;
        if (existingGenres.includes(part.toLowerCase())) return;
        if (/^\d+分钟$/.test(part)) {
          tags.push('<span class="genre-tag douban-tag runtime">' + util.escapeHtml(part) + '</span>');
        } else {
          tags.push('<span class="genre-tag douban-tag">' + util.escapeHtml(part) + '</span>');
        }
      });
    }
    var html = '<div class="douban-meta">';
    if (tags.length) html += '<div class="genre-tags douban-tags">' + tags.join('') + '</div>';
    if (abstract_2) {
      html += '<div class="douban-cast"><span class="cast-label">演员</span> <span class="cast-names">' + util.escapeHtml(abstract_2.replace(/ \/ /g, ' · ')) + '</span></div>';
    } else if (cast.length) {
      html += '<div class="douban-cast"><span class="cast-label">演员</span> <span class="cast-names">' + util.escapeHtml(cast.slice(0, 8).map(function(c) { return c.person?.name; }).filter(Boolean).join(' · ')) + '</span></div>';
    }
    html += '</div>';
    return html;
  }

  function detailHero(item, bodyHtml, castHtml) {
    var bg = util.backdropUrl(item);
    var poster = util.tmdb(item).poster_url || util.artworkUrl(item, "poster") || util.artworkUrl(item, "thumb");

    var pageBg = '';
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
      + (poster ? '<img src="' + poster + '" loading="lazy">' : '<div class="placeholder">' + util.escapeHtml(util.titleOf(item)) + '</div>')
      + '</div>'
      + '<div class="detail-info">' + bodyHtml
      + (castHtml ? '<div class="detail-cast-inline">' + castHtml + '</div>' : '')
      + '</div>'
      + '</div>'
      + '</section>';
  }

  function findFirstEpisode(show) {
    if (!show?.seasons?.length) return null;
    for (var i = 0; i < show.seasons.length; i++) {
      var s = show.seasons[i];
      if (s.episodes?.length) return {season: s, ep: s.episodes[0]};
    }
    return null;
  }

  function renderSeasonCard(show, season, expanded) {
    var epWatched = season.episodes.filter(function(ep) { return state.historyCache[ep.id]; }).length;
    var progressPct = season.episode_count ? Math.round(epWatched / season.episode_count * 100) : 0;
    var sMeta = util.seasonDouban(season);
    var tmdbSeasonData = util.seasonTmdb(season);
    var seasonYear = sMeta.air_date ? sMeta.air_date.toString().slice(0,4) : season.year || show.year || "";
    var seasonPoster = tmdbSeasonData.poster_url || sMeta.poster_url || util.artworkUrl(season, "poster") || "";
    var moreId = "smore-" + show.id + "-" + season.season_number;
    var showMore = state.seasonMoreOpen === moreId;
    var moreHtml = '<div class="season-more-wrap" onclick="event.stopPropagation()">'
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
        : '<div class="placeholder">' + util.escapeHtml(util.titleOf(show)) + '</div>')
      + '</div>'
      + '<div class="card-body"><h4 class="card-title" style="display:inline">' + util.escapeHtml(season.title) + '</h4>'
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
    var sMeta = util.seasonDouban(season);
    var tmdbSeasonData = util.seasonTmdb(season);
    var seasonSynopsis = sMeta.synopsis || tmdbSeasonData.overview || "";
    var seasonPoster = tmdbSeasonData.poster_url || sMeta.poster_url || util.artworkUrl(season, "poster") || "";
    var detailHtml = '';
    if (seasonSynopsis || seasonPoster || sMeta.cast_info || sMeta.air_date) {
      detailHtml = '<div class="season-detail-card">'
        + (seasonPoster ? '<img class="season-detail-poster" src="' + seasonPoster + '" loading="lazy">' : '')
        + '<div class="season-detail-body">'
        + (seasonSynopsis ? '<div class="season-detail-synopsis">' + util.escapeHtml(seasonSynopsis) + '</div>' : '')
        + (sMeta.cast_info ? '<div class="season-detail-cast"><span class="cast-label">主演</span> <span>' + util.escapeHtml(sMeta.cast_info.replace(/\s*\/\s*/g, ' · ')) + '</span></div>' : '')
        + (sMeta.air_date ? '<div class="season-detail-air"><span class="cast-label">年份</span> <span>' + util.escapeHtml(sMeta.air_date) + '</span></div>' : '')
        + '</div></div>';
    }
    return '<div class="inline-episodes">'
      + detailHtml
      + '<div class="episode-list">'
      + (season.episodes || []).map(function(ep) { return renderEpisodeCard(show, season, ep); }).join("")
      + '</div></div>';
  }

  function renderSeasonDoubanTags(show, season) {
    var sMeta = util.seasonDouban(season);
    var d = util.douban(show);
    var abstract = d.abstract || "";
    var tags = [];
    if (abstract) {
      abstract.split(' / ').forEach(function(part) {
        part = part.trim();
        if (!part) return;
        tags.push('<span class="genre-tag douban-tag' + (/^\d+分钟$/.test(part) ? ' runtime' : '') + '">' + util.escapeHtml(part) + '</span>');
      });
    }
    var html = '<div class="douban-meta">';
    if (tags.length) html += '<div class="genre-tags douban-tags">' + tags.join('') + '</div>';
    if (sMeta.cast_info) {
      html += '<div class="douban-cast"><span class="cast-label">演员</span> <span class="cast-names">' + util.escapeHtml(sMeta.cast_info.replace(/ \/ /g, ' · ')) + '</span></div>';
    } else if (d.abstract_2) {
      html += '<div class="douban-cast"><span class="cast-label">演员</span> <span class="cast-names">' + util.escapeHtml(d.abstract_2.replace(/ \/ /g, ' · ')) + '</span></div>';
    }
    html += '</div>';
    return html;
  }

  function episodeEntry(show, season, ep, label) {
    return "{media_id:'" + show.id + "',episode_id:'" + ep.id + "',season_id:'" + season.id + "',type:'episode',path:'" + util.escapeJs(ep.path) + "',title:'" + util.escapeJs(ep.title) + "',show_title:'" + util.escapeJs(util.titleOf(show)) + "',season_number:" + season.season_number + ",episode_number:" + (ep.episode_number || 0) + ",label:'" + util.escapeJs(label) + "',short_label:'S" + String(season.season_number).padStart(2,"0") + "E" + String(ep.episode_number || 0).padStart(2,"0") + "'}";
  }

  function renderEpisodeCard(show, season, ep) {
    var hist = state.getItemHistory(show);
    var active = hist && hist.episode_id === ep.id;
    var label = season.title + " · " + ep.title;
    var entry = episodeEntry(show, season, ep, label);
    var epHist = state.historyCache[ep.id];
    var epm = ep.metadata?.tmdb || {};
    var stillSrc = epm.still_url || util.artworkUrl(ep, "thumb") || util.artworkUrl(ep, "poster");
    var epNum = "S" + String(season.season_number).padStart(2,"0") + "E" + String(ep.episode_number || 0).padStart(2,"0");
    var epName = epm.title || ep.title || ep.filename || epNum;
    var epOverview = epm.overview || ep.overview || "";
    var epRating = epm.rating ? '<span class="ep-badge rating-badge sm">★ ' + Number(epm.rating).toFixed(1) + '</span>' : '';
    var epRuntime = epm.runtime ? '<span class="ep-badge">' + epm.runtime + '分钟</span>' : '';

    return '<div class="episode-row' + (active ? ' active-episode' : '') + '" onclick="playMedia(\'' + util.escapeJs(ep.path) + '\',' + entry + ')">'
      + '<div class="episode-row-thumb">'
      + (stillSrc
        ? '<img src="' + stillSrc + '" loading="lazy" onerror="this.parentElement.innerHTML=\'<div class=\\\'placeholder episode-placeholder\\\'>' + util.escapeHtml(epNum) + '</div>\'">'
        : '<div class="placeholder episode-placeholder">' + util.escapeHtml(epNum) + '</div>')
      + '<div class="play-badge"><span>▶</span></div>'
      + '</div>'
      + '<div class="episode-row-body">'
      + '<div class="episode-row-top">'
      + '<span class="episode-row-num' + (active ? ' active-num' : '') + '">' + epNum + '</span>'
      + '<span class="episode-row-title">' + util.escapeHtml(epName) + '</span>'
      + '<span class="episode-row-meta">' + epRating + epRuntime + '</span>'
      + '</div>'
      + (epOverview ? '<div class="episode-row-overview">' + util.escapeHtml(epOverview) + '</div>' : '')
      + (epHist ? '<div class="episode-row-progress"><div class="bar" style="width:100%"></div></div>' : '')
      + '</div>'
      + '<div class="episode-row-play"><button onclick="event.stopPropagation();playMedia(\'' + util.escapeJs(ep.path) + '\',' + entry + ')" title="播放">▶</button></div>'
      + '</div>';
  }

  /* Expose on MW.detail */
  MW.detail = {
    renderGenreTags: renderGenreTags,
    renderPrimaryMeta: renderPrimaryMeta,
    renderDoubanTags: renderDoubanTags,
    detailHero: detailHero,
    findFirstEpisode: findFirstEpisode,
    renderSeasonCard: renderSeasonCard,
    renderInlineEpisodes: renderInlineEpisodes,
    renderSeasonDoubanTags: renderSeasonDoubanTags,
    episodeEntry: episodeEntry,
    renderEpisodeCard: renderEpisodeCard
  };

})();
