from flask import Flask

from app import db as db_module
from app.config import get_config


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)

    cfg = get_config()

    app.config.update(
        SECRET_KEY=cfg.SECRET_KEY,
        DATABASE=cfg.DATABASE,
        TESTING=cfg.TESTING,
        CONFIG=cfg,
    )

    if test_config:
        app.config.update(test_config)

    db_module.init_app(app)

    with app.app_context():
        db_module.init_db()

    @app.context_processor
    def inject_globals():
        from app.config import get_config
        return {"config": get_config()}

    @app.template_filter("wordle_tiles")
    def wordle_tiles_filter(text: str):
        """Convert Wordle emoji into CSS-styled spans that respect colorblind mode."""
        from markupsafe import Markup, escape
        _MAP = {
            "\U0001f7e9": "correct",   # 🟩 green
            "\U0001f7e8": "present",   # 🟨 yellow
            "⬛":     "absent",    # ⬛ black
            "⬜":     "absent",    # ⬜ white
            "\U0001f7eb": "absent",    # 🟫 brown
            "\U0001f7e6": "present",   # 🟦 blue (colorblind share)
            "\U0001f7e7": "correct",   # 🟧 orange (colorblind share)
        }
        parts = []
        for ch in text:
            cls = _MAP.get(ch)
            if cls:
                parts.append(f'<span class="wt {cls}"></span>')
            else:
                parts.append(str(escape(ch)))
        return Markup("".join(parts))

    # Register blueprints
    from app.auth.routes import bp as auth_bp
    from app.ui.routes import bp as ui_bp
    from app.tournaments.routes import bp as tournaments_bp
    from app.api.routes import bp as api_bp
    from app.pwa.routes import bp as pwa_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(ui_bp)
    app.register_blueprint(tournaments_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(pwa_bp)

    # Serve sw.js at root so its scope covers all app pages (not just /static/js/)
    @app.route("/sw.js")
    def service_worker():
        import os
        from flask import Response
        sw_path = os.path.join(app.static_folder, "js", "sw.js")
        with open(sw_path) as f:
            content = f.read()
        return Response(content, mimetype="application/javascript")

    # Start auto-miss scheduler (disabled during tests)
    if not app.config.get("TESTING"):
        from app.tournaments.scheduler import start_scheduler
        start_scheduler(app)

    return app
