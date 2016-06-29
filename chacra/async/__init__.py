from datetime import timedelta
import os
import pecan

from celery import Celery
from celery.signals import worker_init
from chacra import models


@worker_init.connect
def bootstrap_pecan(signal, sender):
    try:
        config_path = os.environ['PECAN_CONFIG']
    except KeyError:
        here = os.path.abspath(os.path.dirname(__file__))
        # XXX this will not hold true when installing as a binary
        config_path = os.path.abspath(os.path.join(here, '../config/config.py'))

    pecan.configuration.set_config(config_path, overwrite=True)
    # Once configuration is set we need to initialize the models so that we can connect
    # to the DB wth a configured mapper.
    models.init_model()


app = Celery(
    'chacra.async',
    broker='amqp://guest@localhost//',
    include=['chacra.async.rpm', 'chacra.async.debian', 'chacra.async.recurring']
)


def configure_celerybeat():
    try:
        seconds = pecan.conf.polling_cycle
    except AttributeError:
        bootstrap_pecan(None, None)
        seconds = pecan.conf.polling_cycle

    app.conf.update(
        CELERYBEAT_SCHEDULE={
            'poll-repos': {
                'task': 'chacra.async.recurring.poll_repos',
                'schedule': timedelta(
                    seconds=seconds),
                'options': {'queue': 'poll_repos'}
            },
        },
    )

configure_celerybeat()


# helpers
#
#
def post_status(state, json):
    """
    Nicer interface to send a status report on repo creation if configured.

    :param state: Any useful (single-word) string to describe the current
                  status of a repo. Like: 'queued', 'building', 'ready', 'requested'
    :param json: The actual ``json`` representing the Repo model object (or any subset of it)
    :param project_name: The name of the project the repository belongs to
    """
    if not getattr(pecan.conf, 'callback_url', False):
        return
    from chacra.async import recurring
    json['state'] = state
    project_name = json['project_name']
    recurring.callback.apply_async(
        args=(json, project_name),
    )


def post_requested(repo):
    json = repo.__json__()
    post_status('requested', json)


def post_queued(repo):
    json = repo.__json__()
    post_status('queued', json)


def post_building(repo):
    json = repo.__json__()
    post_status('building', json)


def post_ready(repo):
    json = repo.__json__()
    post_status('ready', json)
