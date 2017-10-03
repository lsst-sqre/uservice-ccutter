__all__ = ['get_template']

from flask import jsonify, current_app

from . import api
from ..templatecache import refresh_cache, get_single_project_type


@api.route("/ccutter/<ptype>", methods=["GET"])
@api.route("/ccutter/<ptype>/", methods=["GET"])
def get_template(ptype):
    """Get a single project template.
    """
    refresh_cache(current_app, current_app.config['max_cache_age'])
    return jsonify(get_single_project_type(ptype))
