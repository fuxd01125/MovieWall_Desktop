from flask import Flask

from moviewall.config import APP_DIR


def create_app():
    app = Flask(
        __name__,
        template_folder=str(APP_DIR / "templates"),
        static_folder=str(APP_DIR / "static"),
    )
    from moviewall.routes import register_routes
    register_routes(app)
    return app


app = create_app()
