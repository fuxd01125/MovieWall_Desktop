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
