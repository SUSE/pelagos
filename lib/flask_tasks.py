#
# mostly copied from https://github.com/miguelgrinberg/flack/commit/0c372464b341a2df60ef8d93bdca2001009a42b5?diff=unified
# video https://www.youtube.com/watch?v=tdIIJuPh3SI&feature=youtu.be
#
from functools import wraps
import threading
import time
import uuid
import logging
import sys
import traceback
import json

from flask import Blueprint, abort, current_app, g, request, jsonify
from werkzeug.exceptions import HTTPException, InternalServerError
from flask import url_for as _url_for, current_app, _request_ctx_stack

logging.basicConfig(format='%(asctime)s | %(name)s | %(message)s',
                    level=logging.DEBUG)


tasks_bp = Blueprint('tasks', __name__)
tasks = {}
testing = False


def timestamp():
    """Return the current timestamp as an integer."""
    return int(time.time())


def url_for(*args, **kwargs):
    """
    url_for replacement that works even when there is no request context.
    """
    if '_external' not in kwargs:
        kwargs['_external'] = False
    reqctx = _request_ctx_stack.top
    if reqctx is None:
        if kwargs['_external']:
            raise RuntimeError('Cannot generate external URLs without a '
                               'request context.')
        with current_app.test_request_context():
            return _url_for(*args, **kwargs)
    return _url_for(*args, **kwargs)


@tasks_bp.before_app_first_request
def before_first_request():
    """Start a background thread that cleans up old tasks."""
    def clean_old_tasks():
        logging.debug("Cleanup old tasks")
        """
        This function cleans up old tasks from our in-memory data structure.
        """
        global tasks
        while True:
            # Only keep tasks that are running or that finished less than 5
            # minutes ago.
            five_min_ago = timestamp() - 5 * 60
            tasks = {id: task for id, task in tasks.items()
                     if 't' not in task or task['t'] > five_min_ago}
            time.sleep(60)

    if not testing:
        logging.debug("Production mode, run cleanups")
        thread = threading.Thread(target=clean_old_tasks)
        #thread.start()
    else:
        logging.debug("Testing mode, no cleanup!")


def async_task(f):
    """
    This decorator transforms a sync route to asynchronous by running it
    in a background thread.
    """
    @wraps(f)
    def wrapped(*args, **kwargs):
        def task(app, environ):
            # Create a request context similar to that of the original request
            # so that the task can have access to flask.g, flask.request, etc.
            with app.request_context(environ):
                try:
                    # Run the route function and record the response
                    logging.debug("Executing target function")
                    tasks[task_id]['starttime'] = timestamp()
                    tasks[task_id]['endtime'] = -1
                    tasks[task_id]['started'] = True
                    tasks[task_id]['rv'] = f(*args, **kwargs)
                except HTTPException as e:
                    logging.debug("Caught http exception:" + str(e))
                    tasks[task_id]['rv'] = current_app.handle_http_exception(e)
                    traceback.print_exc(file=sys.stdout)
                except Exception as e:
                    logging.debug("Caught exception:" + str(e))
                    # The function raised an exception, so we set a 500 error
                    tasks[task_id]['rv'] = InternalServerError()
                    traceback.print_exc(file=sys.stdout)
                finally:
                    # We record the time of the response, to help in garbage
                    # collecting old tasks
                    tasks[task_id]['status'] = 'done'
                    logging.debug("target function completed")
                    tasks[task_id]['endtime'] = timestamp()

        # Assign an id to the asynchronous task
        task_id = uuid.uuid4().hex

        # Record the task, and then launch it
        tasks[task_id] = {'task': threading.Thread(
            target=task, args=(current_app._get_current_object(),
                               request.environ))}
        tasks[task_id]['task'].start()
        # wait is needed for case when many requests is done
        # and new thread starting took time
        i = 0
        while i < 30:
            i = i + 1
            if 'started' in tasks[task_id]:
                break
            time.sleep(1)
        if 'started' not in tasks[task_id]:
            tasks[task_id]['rv'] = InternalServerError(
                'Too long async thread starts')
            traceback.print_exc(file=sys.stdout)

        # Return a 202 response, with a link that the client can use to
        # obtain task status
        return '', 202, {'Location': url_for('tasks.get_status', id=task_id),
                         'TaskID': task_id}
    return wrapped


@tasks_bp.route('/status/<id>', methods=['GET'])
def get_status(id):
    """
    Return synchronous task status. If this request returns a 202
    status code, it means that task hasn't finished yet. Else, the response
    from the task is returned.
    """
    task = tasks.get(id)
    logging.debug("Task %s:%s" % (id, str(task)))
    if task is None:
        abort(404)
    repr(task)
    if 'rv' not in task:
        return '', 202, {'Location': url_for('tasks.get_status', id=id),
                         'StartTime': task['starttime'],
                         'EndTime': task['endtime'],
                         'TaskID': id,
                         'status': 'not completed'}
    return task['rv']


@tasks_bp.route('/statuses', methods=['GET'])
def get_statuses():
    """
    Return asynchronous task statuses per task. If this request returns a 202
    status code, it means that task hasn't finished yet. Else, the response
    from the task is returned.
    """
    # logging.info('List current active provisions')
    # logging.debug("tasks:")
    res = dict()
    for task in tasks:
        # logging.debug(tasks[task])
        # logging.debug(tasks[task]['starttime'])
        t = dict()
        t['start_time'] = tasks[task]['starttime']
        t['end_time'] = tasks[task]['endtime']
        if 'rv' in tasks[task]:
            rv = tasks[task]['rv']
            t['rv'] = json.loads(
                rv.get_data().decode(sys.getdefaultencoding()))
            t['status'] = 'done'
        else:
            t['status'] = 'not completed'
        res[task] = t
    logging.debug(res)
    return jsonify(res)


@tasks_bp.route('/cancel/<id>', methods=['GET'])
def cancel_provision(node_id):
    abort(404, "No node [{}] found".format(node_id))
