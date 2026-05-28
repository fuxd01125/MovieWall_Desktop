/* ============================================================
   MovieWall — Settings UI
   Tabbed settings panel, per-item Douban config
   Depends on: mw-utils.js, mw-state.js
   ============================================================ */

window.MW = window.MW || {};

(function() {
  "use strict";

  var util = MW.util;
  var state = MW.state;

  /* ── Per-item Douban state (unchanged from original) ─────────── */

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

  /* ── Settings Panel State ────────────────────────────────────── */

  var settingsData = null;
  var settingsSchema = null;
  var activeSection = "library";

  var SECTION_META = {
    library:  {icon: "📁", label: "媒体库"},
    tmdb:     {icon: "🎬", label: "TMDB"},
    douban:   {icon: "📖", label: "豆瓣"},
    player:   {icon: "▶",  label: "播放器"},
    advanced: {icon: "⚙",  label: "高级"}
  };

  /* ── Load Settings from API ──────────────────────────────────── */

  async function loadSettings() {
    var res = await fetch("/api/settings");
    var data = await res.json();
    settingsData = data.settings;
    settingsSchema = data.schema;
  }

  /* ── Render Settings Page ────────────────────────────────────── */

  async function renderSettings() {
    if (typeof stopHistoryPolling === 'function') stopHistoryPolling();
    state.navStack = [];
    if (typeof renderCategoryTabs === 'function') renderCategoryTabs();
    if (typeof renderBreadcrumb === 'function') renderBreadcrumb();

    var app = document.querySelector("#app");
    app.innerHTML = '<section class="section"><div style="display:flex;align-items:center;gap:12px;margin-bottom:20px"><h2 style="margin:0">设置</h2></div><div class="settings-panel-loading" style="color:var(--muted);padding:40px 0">加载中...</div></section>';

    await loadSettings();

    if (!settingsData || !settingsSchema) {
      app.innerHTML = '<section class="section"><div class="settings-panel-loading" style="color:var(--brand);padding:40px 0">加载设置失败</div></section>';
      return;
    }

    renderSettingsPanel();
  }

  function renderSettingsPanel() {
    var app = document.querySelector("#app");

    /* Douban per-item section (unchanged) */
    var doubanSection = '';
    if (settingDoubanItemId) {
      var item = state.findItem(settingDoubanItemId);
      var itemD = item ? util.douban(item) : {};
      var curRating = itemD.rating || "";
      var curSynopsis = itemD.synopsis || "";
      var doubanUrl = settingDoubanId ? ('https://movie.douban.com/subject/' + settingDoubanId + '/') : '';
      doubanSection = '<div style="margin-bottom:24px;padding:16px 20px;background:rgba(229,9,20,.06);border:1px solid rgba(229,9,20,.15);border-radius:var(--radius-lg)"><div style="display:flex;align-items:center;gap:8px;margin-bottom:12px"><span style="font-size:16px">📖</span><h3 style="margin:0;font-size:15px">豆瓣关联</h3></div>'
        + '<p class="settings-hint">豆瓣目前无法自动爬取数据（WAF 屏蔽），请输入豆瓣 ID 后手动填写评分和剧情简介。豆瓣 ID 可在豆瓣网页 URL 中找到，如 <code>https://movie.douban.com/subject/<strong>10440076</strong>/</code></p>'
        + '<div class="settings-cat-row"><input id="doubanIdInput" style="flex:0.4" value="' + util.escapeHtml(settingDoubanId) + '" placeholder="豆瓣 ID"><input id="doubanRating" style="flex:0.15" value="' + util.escapeHtml(String(curRating)) + '" placeholder="评分"><button onclick="saveDoubanId()">保存</button>'
        + (doubanUrl ? '<button class="ghost" onclick="window.open(\'' + doubanUrl + '\')">打开豆瓣页</button>' : '')
        + '<button class="ghost" onclick="settingDoubanItemId=\'\';navigateTo({type:\'detail\', id:\'' + util.escapeJs(settingDoubanItemId) + '\'})">取消</button></div>'
        + '<div class="settings-cat-row" style="margin-top:6px"><textarea id="doubanSynopsis" style="flex:1;min-height:60px;padding:8px;border-radius:8px;background:rgba(255,255,255,.05);border:1px solid var(--line);color:var(--text);font-family:var(--font);font-size:13px;resize:vertical" placeholder="剧情简介（可选）">' + util.escapeHtml(curSynopsis) + '</textarea></div>'
        + '</div>';
    }

    /* Nav */
    var navHtml = '';
    var sectionKeys = Object.keys(SECTION_META);
    for (var i = 0; i < sectionKeys.length; i++) {
      var key = sectionKeys[i];
      var meta = SECTION_META[key];
      var cls = key === activeSection ? ' active' : '';
      navHtml += '<div class="settings-nav-item' + cls + '" onclick="MW.settings.switchSection(\'' + key + '\')">'
        + '<span class="settings-nav-icon">' + meta.icon + '</span>'
        + '<span>' + meta.label + '</span></div>';
    }

    /* Body */
    var bodyHtml = renderSectionContent(activeSection);

    /* Save bar */
    var saveBar = '<div class="settings-save-bar" id="settingsSaveBar">'
      + '<button onclick="MW.settings.saveAllSettings()">保存设置</button>'
      + '<button class="ghost" onclick="goHome()">返回首页</button>'
      + '<span class="save-hint" id="saveHint"></span>'
      + '</div>';

    app.innerHTML = '<section class="section">'
      + doubanSection
      + '<div class="settings-panel">'
      + '<div class="settings-nav">' + navHtml + '</div>'
      + '<div class="settings-body" id="settingsBody">' + bodyHtml + '</div>'
      + '</div>'
      + saveBar
      + '</section>';

    if (settingDoubanItemId) {
      var inp = document.getElementById("doubanIdInput");
      if (inp) setTimeout(function() { inp.focus(); }, 100);
    }
  }

  /* ── Switch Section ──────────────────────────────────────────── */

  function switchSection(key) {
    activeSection = key;
    /* Update nav active state */
    var navItems = document.querySelectorAll('.settings-nav-item');
    for (var i = 0; i < navItems.length; i++) {
      navItems[i].classList.toggle('active', i === Object.keys(SECTION_META).indexOf(key));
    }
    /* Update body */
    var body = document.getElementById('settingsBody');
    if (body) body.innerHTML = renderSectionContent(key);
  }

  /* ── Render Section Content ──────────────────────────────────── */

  function renderSectionContent(section) {
    var meta = SECTION_META[section];
    var html = '<h3 class="settings-body-header">' + meta.icon + ' ' + meta.label + '</h3>';

    /* Group fields by section */
    var fields = [];
    var schemaKeys = Object.keys(settingsSchema);
    for (var i = 0; i < schemaKeys.length; i++) {
      var key = schemaKeys[i];
      if (settingsSchema[key].section === section) {
        fields.push(key);
      }
    }

    /* Special sections */
    if (section === 'library') {
      html += renderLibrarySection(fields);
    } else if (section === 'player') {
      html += renderPlayerSection();
    } else {
      for (var j = 0; j < fields.length; j++) {
        html += renderSettingField(fields[j]);
      }
    }

    return html;
  }

  /* ── Library Section (special: includes categories editor) ───── */

  function renderLibrarySection(fields) {
    var html = '';
    for (var i = 0; i < fields.length; i++) {
      var key = fields[i];
      if (key === 'categories') {
        html += renderCategoriesEditor();
      } else {
        html += renderSettingField(key);
      }
    }
    return html;
  }

  function renderCategoriesEditor() {
    var cats = settingsData.categories || {};
    var rows = '';
    var keys = Object.keys(cats);
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      var v = typeof cats[k] === 'string' ? cats[k] : (cats[k] && cats[k].name || '');
      rows += '<div class="settings-cat-row">'
        + '<input class="sc-folder" value="' + util.escapeHtml(k) + '" placeholder="文件夹名">'
        + '<input class="sc-name" value="' + util.escapeHtml(v) + '" placeholder="显示名">'
        + '<button class="ghost" onclick="this.closest(\'.settings-cat-row\').remove()">✕</button></div>';
    }
    return '<div class="setting-field" style="flex-direction:column;align-items:stretch">'
      + '<div class="setting-info"><div class="setting-label">目录分类</div>'
      + '<div class="setting-desc">将媒体库文件夹映射为显示名称。修改后需重新扫描。</div></div>'
      + '<div id="settingsCats" style="margin-top:10px">' + (rows || '<div style="color:var(--muted);font-size:13px;padding:8px 0">暂无分类</div>') + '</div>'
      + '<div class="settings-actions"><button class="ghost" onclick="MW.settings.addCatRow()">+ 添加分类</button></div>'
      + '</div>';
  }

  /* ── Player Section (special: list editor) ───────────────────── */

  function renderPlayerSection() {
    var players = settingsData.players || [];
    var rows = '';
    for (var i = 0; i < players.length; i++) {
      var p = players[i];
      rows += '<div class="player-row">'
        + '<input class="player-name" value="' + util.escapeHtml(p.name || '') + '" placeholder="名称">'
        + '<input class="player-path" value="' + util.escapeHtml(p.path || '') + '" placeholder="播放器路径">'
        + '<button class="ghost" onclick="this.closest(\'.player-row\').remove()">✕</button></div>';
    }
    return '<div class="setting-field" style="flex-direction:column;align-items:stretch">'
      + '<div class="setting-info"><div class="setting-label">播放器列表</div>'
      + '<div class="setting-desc">配置可用的媒体播放器，支持 PotPlayer、VLC 等。路径需指向可执行文件。</div></div>'
      + '<div class="player-list-editor" id="playerListEditor" style="margin-top:10px">'
      + (rows || '<div style="color:var(--muted);font-size:13px;padding:8px 0">暂无播放器</div>')
      + '</div>'
      + '<div class="settings-actions"><button class="ghost" onclick="MW.settings.addPlayerRow()">+ 添加播放器</button></div>'
      + '</div>';
  }

  /* ── Render Single Setting Field ─────────────────────────────── */

  function renderSettingField(key) {
    var schema = settingsSchema[key];
    if (!schema) return '';
    var value = settingsData[key];
    if (value === undefined || value === null) value = schema["default"];

    var control = '';
    var t = schema.type;

    if (t === 'bool') {
      var checked = value ? ' checked' : '';
      control = '<label class="toggle-switch"><input type="checkbox" data-key="' + key + '"' + checked + ' onchange="MW.settings.onFieldChange()"><span class="toggle-track"></span></label>';
    } else if (t === 'select') {
      var opts = schema.options || [];
      var options = '';
      for (var i = 0; i < opts.length; i++) {
        var sel = opts[i] === value ? ' selected' : '';
        options += '<option value="' + util.escapeHtml(opts[i]) + '"' + sel + '>' + util.escapeHtml(opts[i]) + '</option>';
      }
      control = '<select data-key="' + key + '" onchange="MW.settings.onFieldChange()">' + options + '</select>';
    } else if (t === 'int') {
      control = '<input type="number" step="1" data-key="' + key + '" value="' + util.escapeHtml(String(value)) + '" oninput="MW.settings.onFieldChange()">';
    } else if (t === 'float') {
      control = '<input type="number" step="0.1" data-key="' + key + '" value="' + util.escapeHtml(String(value)) + '" oninput="MW.settings.onFieldChange()">';
    } else {
      control = '<input type="text" data-key="' + key + '" value="' + util.escapeHtml(String(value)) + '" oninput="MW.settings.onFieldChange()">';
    }

    return '<div class="setting-field">'
      + '<div class="setting-info"><div class="setting-label">' + util.escapeHtml(schema.label) + '</div>'
      + '<div class="setting-desc">' + util.escapeHtml(schema.desc || '') + '</div></div>'
      + '<div class="setting-control">' + control + '</div>'
      + '</div>';
  }

  /* ── Field Change Handler (dirty tracking) ───────────────────── */

  function onFieldChange() {
    var bar = document.getElementById('saveHint');
    if (bar) {
      bar.textContent = '有未保存的修改';
      bar.className = 'save-hint warn';
    }
  }

  /* ── Add Rows ────────────────────────────────────────────────── */

  function addCatRow() {
    var container = document.getElementById("settingsCats");
    if (!container) return;
    /* Remove "暂无分类" placeholder if present */
    var empty = container.querySelector('div[style]');
    if (empty && container.children.length === 1) container.innerHTML = '';
    var div = document.createElement("div");
    div.className = "settings-cat-row";
    div.innerHTML = '<input class="sc-folder" placeholder="文件夹名"><input class="sc-name" placeholder="显示名"><button class="ghost" onclick="this.closest(\'.settings-cat-row\').remove()">✕</button>';
    container.append(div);
    onFieldChange();
  }

  function addPlayerRow() {
    var container = document.getElementById("playerListEditor");
    if (!container) return;
    var empty = container.querySelector('div[style]');
    if (empty && container.children.length === 1) container.innerHTML = '';
    var div = document.createElement("div");
    div.className = "player-row";
    div.innerHTML = '<input class="player-name" placeholder="名称"><input class="player-path" placeholder="播放器路径"><button class="ghost" onclick="this.closest(\'.player-row\').remove()">✕</button>';
    container.append(div);
    onFieldChange();
  }

  /* ── Collect & Save ──────────────────────────────────────────── */

  async function saveAllSettings() {
    var payload = {};

    /* Collect standard fields */
    var controls = document.querySelectorAll('[data-key]');
    for (var i = 0; i < controls.length; i++) {
      var el = controls[i];
      var key = el.getAttribute('data-key');
      var schema = settingsSchema[key];
      if (!schema) continue;
      var t = schema.type;
      if (t === 'bool') {
        payload[key] = el.checked;
      } else if (t === 'int') {
        payload[key] = parseInt(el.value, 10) || schema["default"];
      } else if (t === 'float') {
        payload[key] = parseFloat(el.value) || schema["default"];
      } else {
        payload[key] = el.value;
      }
    }

    /* Collect categories */
    var catRows = document.querySelectorAll('#settingsCats .settings-cat-row');
    if (catRows.length > 0) {
      var cats = {};
      for (var c = 0; c < catRows.length; c++) {
        var row = catRows[c];
        var folder = row.querySelector('.sc-folder');
        var name = row.querySelector('.sc-name');
        if (folder && name) {
          var f = folder.value.trim();
          var n = name.value.trim();
          if (f && n) cats[f] = n;
        }
      }
      payload.categories = cats;
    }

    /* Collect players */
    var playerRows = document.querySelectorAll('#playerListEditor .player-row');
    if (playerRows.length > 0) {
      var players = [];
      for (var p = 0; p < playerRows.length; p++) {
        var pr = playerRows[p];
        var nameInput = pr.querySelector('.player-name');
        var pathInput = pr.querySelector('.player-path');
        if (nameInput && pathInput) {
          var pn = nameInput.value.trim();
          var pp = pathInput.value.trim();
          if (pn && pp) players.push({name: pn, path: pp});
        }
      }
      payload.players = players;
    }

    /* Disable button during save */
    var btn = document.querySelector('.settings-save-bar button');
    if (btn) { btn.disabled = true; btn.textContent = '保存中...'; }

    try {
      var res = await fetch("/api/settings", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
      var data = await res.json();

      if (!data.ok) {
        util.showToast("保存失败: " + (data.error || "未知错误"), 4000);
        return;
      }

      /* Update local state */
      settingsData = data.settings;
      state.categoriesConfig = MW.state.normalizeCategoriesConfig(data.settings.categories);

      /* Feedback */
      var hint = document.getElementById('saveHint');
      if (data.restart_required) {
        util.showToast("部分设置需重启应用后生效", 3000);
        if (hint) { hint.textContent = '需重启应用生效'; hint.className = 'save-hint warn'; }
      } else if (data.rescan_required) {
        util.showToast("设置已保存，建议重新扫描媒体库", 3000);
        if (hint) { hint.textContent = '建议重新扫描'; hint.className = 'save-hint warn'; }
      } else {
        util.showToast("设置已保存");
        if (hint) { hint.textContent = '已保存'; hint.className = 'save-hint'; }
      }

      /* If categories changed, trigger scan */
      if (data.rescan_required && 'categories' in payload) {
        setTimeout(function() {
          document.querySelector("#scanBtn").click();
        }, 800);
      }
    } catch(e) {
      util.showToast("保存失败: 网络错误", 4000);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '保存设置'; }
    }
  }

  /* ── Expose on MW.settings ───────────────────────────────────── */

  MW.settings = {
    openDoubanSetting: openDoubanSetting,
    saveDoubanId: saveDoubanId,
    renderSettings: renderSettings,
    switchSection: switchSection,
    onFieldChange: onFieldChange,
    addCatRow: addCatRow,
    addPlayerRow: addPlayerRow,
    saveAllSettings: saveAllSettings
  };

  /* Expose on window for inline onclick handlers */
  window.openDoubanSetting = openDoubanSetting;
  window.saveDoubanId = saveDoubanId;
  window.renderSettings = renderSettings;

})();
