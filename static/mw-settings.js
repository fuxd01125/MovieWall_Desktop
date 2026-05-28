/* ============================================================
   MovieWall — Settings UI
   Settings page rendering, Douban config, category management
   Depends on: mw-utils.js, mw-state.js
   ============================================================ */

window.MW = window.MW || {};

(function() {
  "use strict";

  var util = MW.util;
  var state = MW.state;

  /* Local state for Douban settings */
  var settingDoubanId = "";
  var settingDoubanItemId = "";

  function openDoubanSetting(itemId, currentDoubanId) {
    state.moreMenuOpen = null;
    state.seasonMoreOpen = null;
    settingDoubanItemId = itemId;
    settingDoubanId = currentDoubanId || "";
    renderSettings();
  }

  async function saveDoubanId() {
    var id = settingDoubanId.trim();
    var itemId = settingDoubanItemId;
    if (!itemId) return;
    var rating = document.getElementById("doubanRating")?.value?.trim();
    var synopsis = document.getElementById("doubanSynopsis")?.value?.trim();
    var body = {douban_id: id};
    if (rating) body.rating = parseFloat(rating);
    if (synopsis) body.synopsis = synopsis;
    var res = await fetch("/api/metadata/douban/" + itemId, {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
    var data = await res.json();
    if (data.douban) {
      util.showToast("豆瓣数据已更新");
    } else if (id) {
      util.showToast("未找到该豆瓣ID的数据（已保存ID，可手动输入评分）", 4000);
    } else {
      util.showToast("已清除豆瓣ID");
    }
    settingDoubanItemId = "";
    settingDoubanId = "";
    var libRes = await fetch("/api/library");
    state.library = await libRes.json();
    if (typeof navigateTo === 'function') navigateTo({type:"detail", id: itemId});
  }

  function renderSettings() {
    if (typeof stopHistoryPolling === 'function') stopHistoryPolling();
    state.navStack = [];
    if (typeof renderCategoryTabs === 'function') renderCategoryTabs();
    if (typeof renderBreadcrumb === 'function') renderBreadcrumb();
    var catKeys = Object.keys(state.categoriesConfig);
    var rows = catKeys.map(function(key) {
      return '<div class="settings-cat-row"><input class="sc-folder" value="' + util.escapeHtml(key) + '" placeholder="文件夹名"><input class="sc-name" value="' + util.escapeHtml(state.categoriesConfig[key].name) + '" placeholder="显示名"><button class="ghost" onclick="this.closest(\'.settings-cat-row\').remove()">✕</button></div>';
    }).join("");

    var doubanSection = '';
    if (settingDoubanItemId) {
      var item = state.findItem(settingDoubanItemId);
      var itemD = item ? util.douban(item) : {};
      var curRating = itemD.rating || "";
      var curSynopsis = itemD.synopsis || "";
      var doubanUrl = settingDoubanId ? ('https://movie.douban.com/subject/' + settingDoubanId + '/') : '';
      doubanSection = '<div class="settings-section"><div class="section-header"><h2>豆瓣关联</h2></div>'
        + '<p class="settings-hint">豆瓣目前无法自动爬取数据（WAF 屏蔽），请输入豆瓣 ID 后手动填写评分和剧情简介。</p>'
        + '<p class="settings-hint">豆瓣 ID 可在豆瓣网页 URL 中找到，如 <code>https://movie.douban.com/subject/<strong>10440076</strong>/</code></p>'
        + '<div class="settings-cat-row"><input id="doubanIdInput" style="flex:0.4" value="' + util.escapeHtml(settingDoubanId) + '" placeholder="豆瓣 ID"><input id="doubanRating" style="flex:0.15" value="' + util.escapeHtml(String(curRating)) + '" placeholder="评分"><button onclick="saveDoubanId()">保存</button>'
        + (doubanUrl ? '<button class="ghost" onclick="window.open(\'' + doubanUrl + '\')">打开豆瓣页</button>' : '')
        + '<button class="ghost" onclick="settingDoubanItemId=\'\';navigateTo({type:\'detail\', id:\'' + util.escapeJs(settingDoubanItemId) + '\'})">取消</button></div>'
        + '<div class="settings-cat-row" style="margin-top:6px"><textarea id="doubanSynopsis" style="flex:1;min-height:60px;padding:8px;border-radius:8px;background:rgba(255,255,255,.05);border:1px solid var(--line);color:var(--text);font-family:var(--font);font-size:13px;resize:vertical" placeholder="剧情简介（可选）">' + util.escapeHtml(curSynopsis) + '</textarea></div>'
        + '</div>';
    }

    var app = document.querySelector("#app");
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
      var inp = document.getElementById("doubanIdInput");
      if (inp) setTimeout(function() { inp.focus(); }, 100);
    }
  }

  function addSettingsRow() {
    var container = document.getElementById("settingsCats");
    if (!container) return;
    var div = document.createElement("div");
    div.className = "settings-cat-row";
    div.innerHTML = '<input class="sc-folder" placeholder="文件夹名"><input class="sc-name" placeholder="显示名"><button class="ghost" onclick="this.closest(\'.settings-cat-row\').remove()">✕</button>';
    container.append(div);
  }

  async function saveSettings() {
    var rows = document.querySelectorAll("#settingsCats .settings-cat-row");
    var cats = {};
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var folder = row.querySelector(".sc-folder").value.trim();
      var name = row.querySelector(".sc-name").value.trim();
      if (folder && name) cats[folder] = name;
    }
    var res = await fetch("/api/config", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({categories: cats})});
    var data = await res.json();
    if (data.ok) document.querySelector("#scanBtn").click();
  }

  /* Expose on MW.settings */
  MW.settings = {
    openDoubanSetting: openDoubanSetting,
    saveDoubanId: saveDoubanId,
    renderSettings: renderSettings,
    addSettingsRow: addSettingsRow,
    saveSettings: saveSettings
  };

  /* Expose on window for inline onclick handlers */
  window.openDoubanSetting = openDoubanSetting;
  window.saveDoubanId = saveDoubanId;
  window.renderSettings = renderSettings;
  window.addSettingsRow = addSettingsRow;
  window.saveSettings = saveSettings;

})();
