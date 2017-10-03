"""Create and store the celery app instance.
"""

__all__ = ['create_celery_app', 'celery_app']

from celery import Celery


# This is installed by create_celery_app via create_flask_app so it's
# available to route blueprints.
celery_app = None


def create_celery_app(flask_app):
    """Create the Celery app.

    This implementation is based on
    http://flask.pocoo.org/docs/0.12/patterns/celery/ to leverage the
    Flask config to also configure Celery.
    """
    global celery_app
    celery_app = Celery(flask_app.import_name,
                        backend=flask_app.config['CELERY_RESULT_BACKEND'],
                        broker=flask_app.config['CELERY_BROKER_URL'])
    celery_app.conf.update(flask_app.config)
    TaskBase = celery_app.Task

    class ContextTask(TaskBase):
        abstract = True

        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)

    celery_app.Task = ContextTask
