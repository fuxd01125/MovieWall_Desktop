from flask import Flask

from moviewall.config import PACKAGED_DIR


def create_app():
    app = Flask(
        __name__,
        template_folder=str(PACKAGED_DIR / "templates"),
        static_folder=str(PACKAGED_DIR / "static"),
    )
    from moviewall.routes import register_routes
    register_routes(app)
    return app


app = create_app()
