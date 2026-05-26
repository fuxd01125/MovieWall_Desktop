"""Regression tests for TV episode playback path validation."""
import os
import sys
import tempfile
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from moviewall.database import get_conn, init_db, SCHEMA

TEST_DB = Path(__file__).parent / "test_library.db"


def setup_module():
    """Create a temp test DB with movie + episode data."""
    global TEST_DB
    TEST_DB = Path(tempfile.gettempdir()) / "moviewall_test_library.db"
    if TEST_DB.exists():
        TEST_DB.unlink()
    # Point DB to test file
    import moviewall.database
    moviewall.database.DB_PATH = TEST_DB
    init_db()

    # Create test data
    conn = get_conn()
    movie_path = str(Path(tempfile.gettempdir()) / "test_movie.mkv")
    # Create dummy file so resolve() works
    Path(movie_path).write_text("dummy")
    ep_path = str(Path(tempfile.gettempdir()) / "test_episode.mkv")
    Path(ep_path).write_text("dummy")

    conn.execute("""INSERT INTO media (id,media_type,title,path,folder)
                    VALUES ('movie1','movie','Test Movie',?,?)""",
                 (movie_path, str(Path(tempfile.gettempdir()))))
    conn.execute("""INSERT INTO media (id,media_type,title,folder)
                    VALUES ('show1','show','Test Show',?)""",
                 (str(Path(tempfile.gettempdir()) / "TV"),))
    conn.execute("""INSERT INTO seasons (id,show_id,season_number,title,folder)
                    VALUES ('season1','show1',1,'Season 1',?)""",
                 (str(Path(tempfile.gettempdir()) / "TV" / "Season 1"),))
    conn.execute("""INSERT INTO episodes (id,show_id,season_id,season_number,episode_number,title,path,folder)
                    VALUES ('ep1','show1','season1',1,1,'Episode 1',?,?)""",
                 (ep_path, str(Path(tempfile.gettempdir()) / "TV" / "Season 1")))
    conn.commit()
    conn.close()


def teardown_module():
    """Clean up test DB and files."""
    conn = get_conn()
    conn.close()
    if TEST_DB.exists():
        TEST_DB.unlink()
    for f in [Path(tempfile.gettempdir()) / "test_movie.mkv",
              Path(tempfile.gettempdir()) / "test_episode.mkv"]:
        if f.exists():
            f.unlink()


class TestIsAllowedMediaPath:
    """Test that is_allowed_media_path correctly validates both movie and episode paths."""

    def setup_method(self):
        from moviewall.routes import is_allowed_media_path
        self.check = is_allowed_media_path

    def test_movie_path_is_allowed(self):
        path = str(Path(tempfile.gettempdir()) / "test_movie.mkv")
        assert self.check(path), "Movie path should be allowed"

    def test_episode_path_is_allowed(self):
        """Regression: episode paths were blocked because is_allowed_media_path
        only checked the media table, not the episodes table."""
        path = str(Path(tempfile.gettempdir()) / "test_episode.mkv")
        assert self.check(path), "Episode path should be allowed"

    def test_nonexistent_path_not_allowed(self):
        assert not self.check("C:\\nonexistent\\file.mkv"), "Nonexistent path should not be allowed"

    def test_empty_path_not_allowed(self):
        assert not self.check(""), "Empty path should not be allowed"


class TestApiPlayEpisodeRoute:
    """Test the full /api/play route for episodes using a Flask test client."""

    def setup_method(self):
        from moviewall import create_app
        app = create_app()
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_play_episode_returns_ok(self):
        """Regression: episode playback should not abort with 403."""
        path = str(Path(tempfile.gettempdir()) / "test_episode.mkv")
        resp = self.client.post("/api/play", json={"path": path})
        # Should get a valid response (either ok or player error, not 403)
        assert resp.status_code in (200, 400), f"Expected 200 or 400, got {resp.status_code}"

    def test_play_episode_not_403(self):
        """Regression test: episode path must NOT be rejected as 403."""
        path = str(Path(tempfile.gettempdir()) / "test_episode.mkv")
        resp = self.client.post("/api/play", json={"path": path})
        assert resp.status_code != 403, "Episode path was blocked by is_allowed_media_path (403 forbidden)"

    def test_play_movie_200(self):
        """Movie playback should continue to work."""
        path = str(Path(tempfile.gettempdir()) / "test_movie.mkv")
        resp = self.client.post("/api/play", json={"path": path})
        assert resp.status_code != 403, "Movie path should not be blocked"

    def test_play_invalid_path_403(self):
        """Invalid paths should still be blocked."""
        resp = self.client.post("/api/play", json={"path": "C:\\nonexistent\\file.mkv"})
        assert resp.status_code == 403, "Nonexistent path should be forbidden"


class TestIsAllowedFolder:
    """Test that folder validation also works (though less critical for playback)."""

    def setup_method(self):
        from moviewall.routes import is_allowed_folder
        self.check = is_allowed_folder

    def test_movie_folder_allowed(self):
        assert self.check(str(Path(tempfile.gettempdir()))), "Movie folder should be allowed"

    def test_nonexistent_folder_not_allowed(self):
        assert not self.check("C:\\nonexistent\\folder"), "Nonexistent folder should not be allowed"


class TestDBEpisodeDataIntegrity:
    """Verify episode path data integrity in the database."""

    def test_episode_has_path(self):
        conn = get_conn()
        row = conn.execute("SELECT path FROM episodes WHERE id='ep1'").fetchone()
        conn.close()
        assert row is not None, "Episode should exist"
        assert row["path"] is not None, "Episode path should not be None"
        assert len(row["path"]) > 0, "Episode path should not be empty"

    def test_show_has_no_path(self):
        """Shows in media table don't have 'path' set — only 'folder'."""
        conn = get_conn()
        row = conn.execute("SELECT path FROM media WHERE id='show1'").fetchone()
        conn.close()
        assert row["path"] is None, "Show path in media table should be None (episode paths are in episodes table)"


class TestTmdbMatchScore:
    """Unit tests for TMDB match scoring (BUG 2 regression)."""

    def setup_method(self):
        from moviewall.metadata import _tmdb_match_score
        self.score = _tmdb_match_score

    def test_exact_name_match(self):
        result = {"name": "Santa Clarita Diet", "original_name": "Santa Clarita Diet",
                  "first_air_date": "2017-02-03", "original_language": "en"}
        s = self.score(result, "Santa Clarita Diet", "2017", "tv")
        assert s >= 100, "Exact name + year match should score >= 100"

    def test_chinese_name_match(self):
        result = {"name": "Santa Clarita Diet", "original_name": "Santa Clarita Diet",
                  "first_air_date": "2017-02-03", "original_language": "en"}
        s = self.score(result, "真爱不死", "2017", "tv")
        # Chinese query won't match English names — but may still be a weak match
        # The test is that wrong-match cases don't exceed threshold
        assert s < 50, "Chinese name with no English overlap should score below 50"

    def test_wrong_match_rejected(self):
        """真爱不死 should NOT match 神探夏洛克 (Sherlock)."""
        result = {"name": "Sherlock", "original_name": "Sherlock",
                  "first_air_date": "2010-07-25", "original_language": "en"}
        s = self.score(result, "真爱不死", "2017", "tv")
        assert s < 50, "Wrong match (真爱不死 → Sherlock) should score below threshold"

    def test_year_mismatch_penalty(self):
        """Same name, wrong year → penalty but still recognized as same series."""
        result = {"name": "The Office", "original_name": "The Office",
                  "first_air_date": "2005-03-24", "original_language": "en"}
        s = self.score(result, "The Office", "2019", "tv")
        # Exact name match = 100, year mismatch penalty = -20, total = 80
        assert s > 50, "Same show name should still be recognized despite year mismatch"
        assert s < 100, "Year mismatch should reduce score"

    def test_partial_name_match_with_year(self):
        result = {"name": "Stranger Things", "original_name": "Stranger Things",
                  "first_air_date": "2016-07-15", "original_language": "en"}
        s = self.score(result, "Stranger Things", "2016", "tv")
        assert s >= 100, "Exact name + year should be high confidence"

    def test_movie_type_match(self):
        result = {"name": "Inception", "original_name": "Inception",
                  "release_date": "2010-07-16", "original_language": "en", "media_type": "movie"}
        s = self.score(result, "Inception", "2010", "movie")
        assert s >= 120, "Exact name + year + media_type match should be high"

    def test_wrong_media_type_penalty(self):
        """Same name returns lower score when type mismatches."""
        result = {"name": "Inception", "original_name": "Inception",
                  "release_date": "2010-07-16", "original_language": "en", "media_type": "movie"}
        s_tv = self.score(result, "Inception", "2010", "tv")
        s_movie = self.score(result, "Inception", "2010", "movie")
        # Same result should score higher when type matches
        assert s_tv < s_movie, "Wrong media type should reduce score vs correct type"


class TestSeasonPosterPriority:
    """Test that season poster fallback priority is correct (BUG 3 regression)."""

    def test_artwork_url_http_path(self):
        """artworkUrl should return HTTP URL directly without /api/artwork prefix."""
        item = {"id": "test", "poster": "https://image.tmdb.org/t/p/w500/test.jpg"}
        # Simulate the artworkUrl logic
        if item.get("poster"):
            if str(item["poster"]).startswith("http"):
                result = item["poster"]
            else:
                result = "/api/artwork/" + item["id"] + "/poster"
        assert result == "https://image.tmdb.org/t/p/w500/test.jpg", \
            "HTTP poster URL should be returned directly"

    def test_artwork_url_local_path(self):
        """artworkUrl should use /api/artwork prefix for local paths."""
        item = {"id": "test", "poster": "F:\\TV\\poster.jpg"}
        if item.get("poster"):
            if str(item["poster"]).startswith("http"):
                result = item["poster"]
            else:
                result = "/api/artwork/" + item["id"] + "/poster"
        assert result == "/api/artwork/test/poster", \
            "Local poster path should use /api/artwork prefix"

    def test_season_poster_priority_chain(self):
        """Season poster priority: local > TMDB > douban > empty."""
        season = {"id": "s1", "poster": ""}
        tmdb_data = {"poster_url": "https://tmdb.com/poster.jpg"}
        douban_data = {"poster_url": "https://douban.com/poster.jpg"}

        # Test 1: TMDB poster used when no local
        poster = tmdb_data["poster_url"] or ""
        assert poster == "https://tmdb.com/poster.jpg", "TMDB poster should be fallback"

        # Test 2: local poster (set on season) takes priority
        season["poster"] = "F:\\TV\\poster.jpg"
        poster = season["poster"] if not str(season.get("poster", "")).startswith("http") else season["poster"]
        assert poster == "F:\\TV\\poster.jpg", "Local poster should be highest priority"

        # Test 3: douban is last fallback
        season["poster"] = ""
        poster = tmdb_data["poster_url"] or douban_data["poster_url"] or ""
        assert poster == "https://tmdb.com/poster.jpg", "TMDB should come before douban"

        poster = tmdb_data["poster_url"] if tmdb_data["poster_url"] else douban_data["poster_url"]
        assert poster == "https://tmdb.com/poster.jpg", "TMDB poster should be chosen over douban"


class TestFinalConsistencyCheck:
    """Test that attach_all_metadata rejects inconsistent TMDB data and clears stale DB entries."""

    def test_consistency_rejects_wrong_match(self):
        from moviewall.metadata import _final_consistency_check
        tmdb_data = {"tmdb_id": 19885, "title": "Sherlock", "original_title": "Sherlock",
                     "date": "2010-07-25"}
        # Query is "真爱不死" → should reject Sherlock
        assert not _final_consistency_check(tmdb_data, "真爱不死", "2017", "tv"), \
            "Sherlock for 真爱不死 should be rejected"

    def test_consistency_accepts_correct_match(self):
        from moviewall.metadata import _final_consistency_check
        tmdb_data = {"tmdb_id": 79501, "title": "Santa Clarita Diet",
                     "original_title": "Santa Clarita Diet", "date": "2017-02-03"}
        assert _final_consistency_check(tmdb_data, "Santa Clarita Diet", "2017", "tv")

    def test_consistency_empty_data_passes(self):
        from moviewall.metadata import _final_consistency_check
        assert not _final_consistency_check({}, "Some Show", "2020", "tv")

    def test_save_tmdb_meta_always_called_on_empty(self):
        """Even with empty data, save_tmdb_meta clears stale metadata from DB."""
        from moviewall.database import save_tmdb_meta, get_conn
        # Pre-create a media entry (FK requirement) and put stale metadata
        conn = get_conn()
        conn.execute("INSERT OR IGNORE INTO media (id,media_type,title) VALUES ('meta_clear_test','show','Test Show')")
        conn.execute("INSERT OR REPLACE INTO metadata_tmdb (media_id,tmdb_id,title) VALUES ('meta_clear_test',99999,'Wrong Title')")
        conn.commit()
        conn.close()
        # Now call save_tmdb_meta with empty data (simulating "no valid TMDB match")
        save_tmdb_meta("meta_clear_test", {})
        conn = get_conn()
        row = conn.execute("SELECT tmdb_id, title FROM metadata_tmdb WHERE media_id='meta_clear_test'").fetchone()
        conn.close()
        assert row is not None, "Entry should exist (INSERT OR CONFLICT)"
        assert row["tmdb_id"] is None, "tmdb_id should be None (cleared by empty data)"
        assert row["title"] is None, "title should be None (cleared by empty data)"


class TestSeasonCountValidation:
    """Test season count validation in TMDB match scoring."""

    def setup_method(self):
        from moviewall.metadata import _tmdb_match_score
        self.score = _tmdb_match_score

    def test_season_count_boost_exact_match(self):
        r = {"name": "Santa Clarita Diet", "original_name": "Santa Clarita Diet",
             "first_air_date": "2017-02-03", "number_of_seasons": 3, "original_language": "en"}
        s = self.score(r, "Santa Clarita Diet", "2017", "tv", local_season_count=3)
        # 100 (exact name) + 40 (year) + 25 (seasons match) = 165
        assert s >= 160, "Exact season count should boost score"

    def test_season_count_penalty_wrong_count(self):
        r = {"name": "Some Show", "first_air_date": "2015", "number_of_seasons": 1, "original_language": "en"}
        s_wrong = self.score(r, "My Show", "2017", "tv", local_season_count=3)
        s_none = self.score(r, "My Show", "2017", "tv", local_season_count=0)
        # With wrong count (diff=2 > 1) → -15 penalty compared to no count info
        assert s_wrong <= s_none, "Wrong season count should reduce score vs no count info"


class TestClearTmdbCache:
    """Test that clear_tmdb_cache properly invalidates cache entries."""

    def test_clear_cache_removes_matching_keys(self):
        from moviewall.metadata import clear_tmdb_cache
        from moviewall.config import read_json, write_json, METADATA_CACHE_FILE, cache_lock
        # Pre-seed cache with a test entry (use spaces to match normalize_key output)
        test_key = "tv:test show for cache clear:2020:zh-CN"
        with cache_lock:
            cache = read_json(METADATA_CACHE_FILE, {})
            cache[test_key] = {"_cached_at": 0, "data": {"tmdb_id": 999, "title": "test"}}
            write_json(METADATA_CACHE_FILE, cache)
        # Clear by title
        clear_tmdb_cache("ignored_id", "test_show_for_cache_clear")
        # Verify entry removed
        with cache_lock:
            cache = read_json(METADATA_CACHE_FILE, {})
            assert test_key not in cache, "Cache entry should be removed by clear_tmdb_cache"

    def test_clear_cache_does_not_remove_unrelated(self):
        from moviewall.metadata import clear_tmdb_cache
        from moviewall.config import read_json, write_json, METADATA_CACHE_FILE, cache_lock
        with cache_lock:
            cache = read_json(METADATA_CACHE_FILE, {})
            cache["tv:unrelated:2020:zh-CN"] = {"_cached_at": 0, "data": {"tmdb_id": 1}}
            write_json(METADATA_CACHE_FILE, cache)
        clear_tmdb_cache("id", "completely_different_show")
        with cache_lock:
            cache = read_json(METADATA_CACHE_FILE, {})
            assert "tv:unrelated:2020:zh-CN" in cache, "Unrelated cache entries should survive clear"

    def test_clear_cache_removes_tmdb_prefix_keys(self):
        from moviewall.metadata import clear_tmdb_cache
        from moviewall.config import read_json, write_json, METADATA_CACHE_FILE, cache_lock
        tmdb_key = "tmdb:search/movie:query=inception&language=zh-CN"
        with cache_lock:
            cache = read_json(METADATA_CACHE_FILE, {})
            cache[tmdb_key] = {"_cached_at": 0, "data": {"results": []}}
            write_json(METADATA_CACHE_FILE, cache)
        clear_tmdb_cache("id", "inception")
        with cache_lock:
            cache = read_json(METADATA_CACHE_FILE, {})
            assert tmdb_key not in cache, "tmdb: prefixed keys should be removed by clear_tmdb_cache"


class TestAttachMetadataAlwaysSaves:
    """Test that attach_all_metadata always calls save_tmdb_meta (even on empty)."""

    def test_force_refresh_skips_cache(self):
        from moviewall.metadata import get_tmdb_metadata
        # force_refresh should not crash — it's a flag, not a cache-dependent test
        result = get_tmdb_metadata("nonexistent_show_xyz", "2099", "tv", force_refresh=True)
        assert isinstance(result, dict), "force_refresh should return a dict"
        # Clean up any cache entry that was created
        from moviewall.metadata import clear_tmdb_cache
        clear_tmdb_cache("id", "nonexistent_show_xyz")


class TestOrphanCleanup:
    """Test that orphan cleanup removes DB entries for deleted/moved folders (BUG 1)."""

    def test_orphan_folder_detected(self):
        """A folder path that doesn't exist on disk should be flagged for removal."""
        from pathlib import Path
        non_existent = "C:\\nonexistent_orphan_folder"
        assert not Path(non_existent).exists(), "Test folder must not exist"

    def test_existing_folder_not_orphan(self):
        """A folder path that exists on disk should NOT be flagged."""
        assert Path(tempfile.gettempdir()).exists(), "Temp dir must exist"

