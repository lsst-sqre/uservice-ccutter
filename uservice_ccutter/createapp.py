"""Create the Flask application.
"""

__all__ = ['create_flask_app']

import os

from apikit import APIFlask

from .templatecache import refresh_cache
from .celeryapp import create_celery_app


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

    # Configure redis backend for celery
    default_redis_url = 'redis://localhost:6379'  # default for development
    app.config['CELERY_RESULT_BACKEND'] = os.getenv('REDIS_URL',
                                                    default_redis_url)
    app.config['CELERY_BROKER_URL'] = os.getenv('REDIS_URL',
                                                default_redis_url)

    # Create the Celery app so it's available for the routes
    create_celery_app(app)

    # register blueprints with the routes
    from .routes import api as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix=None)

    # Prime cache at start and then check it on each GET
    refresh_cache(app, app.config['max_cache_age'])

    return app
