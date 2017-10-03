"""Application routes blueprint.
"""

__all__ = ['api']

from flask import Blueprint

# Create api before importing modules because they need it.
api = Blueprint('api', __name__)

from . import errorhandlers
from . import root
from . import projectlist
from . import gettemplate
from . import createproject
