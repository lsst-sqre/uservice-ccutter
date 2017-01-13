#!/usr/bin/env python
"""ccutter microservice framework"""
# Python 2/3 compatibility
try:
    from json.decoder import JSONDecodeError
except ImportError:
    JSONDecodeError = ValueError
from apikit import APIFlask
from apikit import BackendError
from flask import jsonify


def server(run_standalone=False):
    """Create the app and then run it."""
    # Add "/ccutter" for mapping behind api.lsst.codes
    app = APIFlask(name="uservice-ccutter",
                   version="0.0.1",
                   repository="https://github.com/sqre-lsst/uservice-ccutter",
                   description="Bootstrapper for cookiecutter projects",
                   route=["/", "/ccutter"],
                   auth={"type": "none"})

    @app.errorhandler(BackendError)
    # pylint can't understand decorators.
    # pylint: disable=unused-variable
    def handle_invalid_usage(error):
        """Custom error handler."""
        response = jsonify(error.to_dict())
        response.status_code = error.status_code
        return response

    @app.route("/")
    def healthcheck():
        """Default route to keep Ingress controller happy."""
        return "OK"

    @app.route("/ccutter")
    @app.route("/ccutter/")
    # @app.route("/ccutter/<parameter>")
    # or, if you have a parameter, def route_function(parameter=None):
    def route_function():
        """
        Bootstrapper for cookiecutter projects
        """
        # FIXME: service logic goes here
        # - raise errors as BackendError
        # - return your results with jsonify
        # - set status_code on the response as needed
        return

    if run_standalone:
        app.run(host='0.0.0.0', threaded=True)


def standalone():
    """Entry point for running as its own executable."""
    server(run_standalone=True)


if __name__ == "__main__":
    standalone()
