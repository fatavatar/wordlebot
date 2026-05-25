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

    # Start auto-miss scheduler (disabled during tests)
    if not app.config.get("TESTING"):
        from app.tournaments.scheduler import start_scheduler
        start_scheduler(app)

    return app
