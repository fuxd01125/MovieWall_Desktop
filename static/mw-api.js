/* ============================================================
   MovieWall — API Layer
   Pure fetch calls for ratings, history, favorites, playback
   ============================================================ */

window.MW = window.MW || {};

(function() {
  "use strict";

  var util = MW.util;
  var state = MW.state;

  async function apiPutRating(mediaId, score) {
    await fetch("/api/ratings", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({media_id:mediaId, score:score})});
  }

  async function apiDeleteRating(mediaId) {
    await fetch("/api/ratings/" + mediaId, {method:"DELETE"});
  }

  async function apiPutHistory(entry) {
    await fetch("/api/history", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify(entry)});
  }

  async function apiToggleFavorite(mediaId) {
    var res = await fetch("/api/favorites", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({media_id: mediaId})});
    return await res.json();
  }

  async function openFolder(path) {
    await fetch("/api/open_folder", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({path:path})});
  }

  function recordPlay(entry) {
    var item = Object.assign({}, entry, {played_at: Date.now() / 1000});
    state.historyCache[item.media_id] = item;
    state.historyCache.__last = item;
    apiPutHistory(item);
  }

  /* Expose on MW.api */
  MW.api = {
    apiPutRating: apiPutRating,
    apiDeleteRating: apiDeleteRating,
    apiPutHistory: apiPutHistory,
    apiToggleFavorite: apiToggleFavorite,
    openFolder: openFolder,
    recordPlay: recordPlay
  };

  /* Expose on window for inline onclick handlers */
  window.openFolder = openFolder;

})();
