"""Create the Flask application.
"""

__all__ = ['create_flask_app']

from apikit import APIFlask

from .templatecache import refresh_cache


def create_flask_app():
    """Create the Flask app with /ccutter routes behind api.lsst.codes.
    """
    app = APIFlask(name="uservice-ccutter",
                   version="0.0.9",
                   repository="https://github.com/sqre-lsst/uservice-ccutter",
                   description="Bootstrapper for cookiecutter projects",
                   route=["/", "/ccutter"],
                   auth={"type": "basic",
                         "data": {"username": "",
                                  "password": ""}})
    app.config['max_cache_age'] = 60 * 60 * 8  # 8 hours
    app.config["PROJECTTYPE"] = {}
    # Cookiecutter requires the order be preserved.
    app.config["JSON_SORT_KEYS"] = False

    # register blueprints with the routes
    from .routes import api as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix=None)

    # Prime cache at start and then check it on each GET
    refresh_cache(app, app.config['max_cache_age'])

    return app
