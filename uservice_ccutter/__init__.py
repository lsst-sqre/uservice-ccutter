"""SQuaRE cookiecutter service (api.lsst.codes-compliant).
"""

__all__ = ['flask_app']

from .createapp import create_flask_app

flask_app = create_flask_app()
