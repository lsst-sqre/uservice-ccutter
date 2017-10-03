__all__ = ['display_project_types']

from flask import jsonify, current_app

from . import api
from ..templatecache import refresh_cache, get_single_project_type


@api.route("/ccutter")
@api.route("/ccutter/")
def display_project_types():
    """Return cookiecutter.json for each project type.
    """
    refresh_cache(current_app, current_app.config['max_cache_age'])
    retval = {}
    for ptype in current_app.config["PROJECTTYPE"]:
        retval[ptype] = get_single_project_type(current_app, ptype)
    return jsonify(retval)
