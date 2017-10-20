__all__ = ['create_project']

from copy import deepcopy
import json

from apikit import BackendError
from flask import jsonify, request, current_app
from structlog import get_logger

from . import api
from ..tasks.createproject import create_project_as_task


@api.route("/ccutter/<project_type>", methods=["POST"])
@api.route("/ccutter/<project_type>/", methods=["POST"])
def create_project(project_type):
    """Create a new project.
    """
    logger = get_logger()

    # We need authorization to POST.  Raise error if not.
    # FIXME move auth checking to a decorator?
    check_authorization()
    auth = current_app.config["AUTH"]["data"]

    # Get data from request
    request_data = request.get_json()
    if not request_data:
        raise BackendError(reason="Bad Request",
                           status_code=400,
                           content="POST data must not be empty.")

    logger.debug('Original template: %r' %
                 current_app.config["PROJECTTYPE"][project_type]["template"])

    template_values = deepcopy(
        current_app.config["PROJECTTYPE"][project_type]["template"])
    logger.debug('Copied template: %r' % template_values)
    # Necessary for ensuring ordering in template_values (for cookiecutter)
    for key in request_data:
        template_values[key] = request_data[key]
    logger.debug('Template with user data: %r' % template_values)

    serialized_template_values = json.dumps(template_values, indent=4)
    create_project_as_task.apply_async(
        (project_type, auth, serialized_template_values))

    return jsonify({'message': "I’m creating your project. "
                               "Check GitHub in a sec."})


def check_authorization():
    """Set app.auth["data"] if credentials provided, raise an error otherwise.
    """
    logger = get_logger()
    req_auth = request.authorization
    if req_auth is None:
        raise BackendError(reason="Unauthorized",
                           status_code=401,
                           content="No authorization provided.")
    # FIXME look into this: I don't think per-session auth information
    # should go into the **app config**.
    current_app.config["AUTH"]["data"]["username"] = req_auth.username
    current_app.config["AUTH"]["data"]["password"] = req_auth.password
    logger = logger.bind(username=req_auth.username)
