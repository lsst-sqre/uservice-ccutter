"""SQuaRE cookiecutter service (api.lsst.codes-compliant).
"""

from pkg_resources import get_distribution, DistributionNotFound

try:
    __version__ = get_distribution('sqre-uservice-ccutter').version
except DistributionNotFound:
    __version__ = 'unknown'

__all__ = ['flask_app', 'celery_app']

from .createapp import create_flask_app

flask_app = create_flask_app()

from .celeryapp import celery_app
