/* ============================================================
   MovieWall — Person/Actor Page Rendering
   Person detail hero, cast section, person works grid
   Depends on: mw-utils.js, mw-state.js
   ============================================================ */

window.MW = window.MW || {};

(function() {
  "use strict";

  var util = MW.util;
  var state = MW.state;

  function renderCastSection(cast) {
    if (!cast || !cast.length) return '';
    return '<section class="section cast-section">'
      + '<div class="section-header"><h2>演员</h2><small>' + cast.length + ' 人</small></div>'
      + '<div class="cast-scroll">'
      + cast.map(function(c) {
        var p = c.person || {};
        var img = p.profile_url
          ? '<img src="' + p.profile_url + '" loading="lazy" onerror="this.parentElement.innerHTML=\'<div class=\\\'cast-avatar-placeholder\\\'>' + util.escapeHtml((p.name || '?')[0]) + '</div>\'">'
          : '<div class="cast-avatar-placeholder">' + util.escapeHtml((p.name || '?')[0]) + '</div>';
        return '<article class="cast-card" onclick="openPerson(\'' + util.escapeJs(p.id || '') + '\')">'
          + '<div class="cast-avatar">' + img + '</div>'
          + '<div class="cast-info">'
          + '<div class="cast-name">' + util.escapeHtml(p.name || '') + '</div>'
          + '<div class="cast-role">' + util.escapeHtml(c.character || c.job || '') + '</div>'
          + '</div></article>';
      }).join('')
      + '</div></section>';
  }

  async function openPerson(personId) {
    if (!personId) return;
    if (typeof showSkeleton === 'function') showSkeleton();
    else if (MW.cards && MW.cards.showSkeleton) MW.cards.showSkeleton();
    var res = await fetch("/api/person/" + encodeURIComponent(personId));
    if (!res.ok) { util.showToast("演员信息未能加载", 3000); if (typeof goHome === 'function') goHome(); return; }
    var data = await res.json();
    if (typeof navigateTo === 'function') navigateTo({type:"person", data});
  }

  function renderPersonDetail(data) {
    state.currentView = {type:"person", data};
    if (typeof renderCategoryTabs === 'function') renderCategoryTabs();
    if (typeof renderBreadcrumb === 'function') renderBreadcrumb();

    var img = data.profile_url
      ? '<img src="' + data.profile_url + '" loading="lazy">'
      : '<div class="placeholder">' + util.escapeHtml((data.name || '?')[0]) + '</div>';
    var aka = data.also_known_as && data.also_known_as.length
      ? '<div class="person-aka">又名: ' + data.also_known_as.map(function(n) { return util.escapeHtml(n); }).join(' / ') + '</div>' : '';

    var hero = '<div class="person-hero">'
      + '<button class="back-hero-btn" onclick="event.stopPropagation();goBackSmart()" title="返回" aria-label="返回">'
      + '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>'
      + '</button>'
      + '<div class="person-poster">' + img + '</div>'
      + '<div class="person-info">'
      + '<h1>' + util.escapeHtml(data.name || '') + '</h1>'
      + (data.original_name && data.original_name !== data.name ? '<div class="person-original-name">' + util.escapeHtml(data.original_name) + '</div>' : '')
      + (data.known_for_department ? '<div class="person-dept">' + util.escapeHtml(data.known_for_department) + '</div>' : '')
      + (data.birthday ? '<div class="person-meta"><span class="meta-label">出生</span> ' + util.escapeHtml(data.birthday) + (data.deathday ? ' — ' + util.escapeHtml(data.deathday) : '') + '</div>' : '')
      + (data.place_of_birth ? '<div class="person-meta"><span class="meta-label">出生地</span> ' + util.escapeHtml(data.place_of_birth) + '</div>' : '')
      + aka
      + (data.biography ? '<div class="person-bio">' + util.escapeHtml(data.biography) + '</div>' : '')
      + '</div></div>';

    var works = data.works || [];
    var worksHtml = '';
    if (works.length) {
      worksHtml = '<section class="section"><div class="section-header"><h2>本地作品</h2><small>' + works.length + ' 部</small></div>'
        + '<div class="grid">'
        + works.map(function(w) {
          var item = state.findItem(w.media_id);
          var poster = item ? util.artworkUrl(item, "poster") : '';
          var title = w.display_title || w.media_title || '';
          var role = w.character ? '饰 ' + w.character : (w.job || w.department || '');
          return '<article class="card" onclick="openDetail(\'' + util.escapeJs(w.media_id) + '\')">'
            + '<div class="card-poster">'
            + (poster
              ? '<img src="' + poster + '" loading="lazy" onerror="this.parentElement.innerHTML=\'<div class=\\\'placeholder\\\'>' + util.escapeHtml(title) + '</div>\'">'
              : '<div class="placeholder">' + util.escapeHtml(title) + '</div>')
            + '</div>'
            + '<div class="card-body">'
            + '<h4 class="card-title">' + util.escapeHtml(title) + '</h4>'
            + (role ? '<div class="person-role">' + util.escapeHtml(role) + '</div>' : '')
            + '</div></article>';
        }).join('')
        + '</div></section>';
    }

    document.querySelector("#app").innerHTML = '<div class="person-page">' + hero + worksHtml + '</div>';
  }

  /* Expose on MW.person */
  MW.person = {
    renderCastSection: renderCastSection,
    openPerson: openPerson,
    renderPersonDetail: renderPersonDetail
  };

  /* Expose on window for inline onclick handlers */
  window.openPerson = openPerson;

})();
