# coding: utf-8
"""
Defines the client-side Celery "app" (API instance) used by EDD to asynchronously execute tasks on
the Celery cluster.
"""

from __future__ import absolute_import, unicode_literals

from celery import Celery

from kombu.serialization import register

from edd_utils.parsers.json_encoders import (
    datetime_dumps, datetime_loads, EXTENDED_JSON_CONTENT_TYPE
)

####################################################################################################
# Parse settings.py directly instead of the more usual method of using django.conf's settings.
# This module is called from edd's __init__ *before* django finishes parsing settings. Maybe another
# method is possible, but this works :-/
####################################################################################################
from edd.settings import config  # noqa
RABBITMQ_HOST = config['rabbitmq'].get('hostname')
EDD_RABBITMQ_USERNAME = config['rabbitmq'].get('edd_user')
EDD_RABBITMQ_PASSWORD = config['rabbitmq'].get('edd_pass')
RABBITMQ_PORT = config['rabbitmq'].get('port')
EDD_VHOST = config['rabbitmq'].get('edd_vhost')
BROKER_URL = 'amqp://%(user)s:%(pass)s@%(host)s:%(port)s/%(vhost)s' % {
             'user': EDD_RABBITMQ_USERNAME,
             'pass': EDD_RABBITMQ_PASSWORD,
             'host': RABBITMQ_HOST,
             'port': RABBITMQ_PORT,
             'vhost': EDD_VHOST,
}

####################################################################################################
# Register custom serialization code to allow us to serialize datetime objects as JSON (just
# datetimes, for starters). Used by Celery tasks to serialize dates.
####################################################################################################
register(EXTENDED_JSON_CONTENT_TYPE, datetime_dumps, datetime_loads,
         content_type='application/x-' + EXTENDED_JSON_CONTENT_TYPE,
         content_encoding='UTF-8')

# set up a Celery "app" for use by EDD. A Celery "app" is just an unfortunately-named instance of
# the Celery API,
# This instance defines EDD's interface will use to interface with Celery.
task_exchange = Celery('edd', broker=BROKER_URL)

# load configuration from celeryconfig.py file instead of hard-coding here
# using a String here means the worker won't have to pickle the object when
# using Windows. Pickle is insecure for production.
task_exchange.config_from_object('edd.settings')
task_exchange.config_from_object('edd.celeryconfig')

# auto-discover celery tasks in all included Django apps, provided they
# use the tasks.py convention (EDD presently doesn't). If implementing,
# remove CELERY_IMPORTS = ('edd.remote_tasks',) from celeryconfig.py
# task_exchange.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

if __name__ == '__main__':
    task_exchange.start()
