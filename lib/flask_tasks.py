#
# mostly copied from https://github.com/miguelgrinberg/flack/commit/0c372464b341a2df60ef8d93bdca2001009a42b5?diff=unified
# video https://www.youtube.com/watch?v=tdIIJuPh3SI&feature=youtu.be
#
import ctypes
import json
import logging
import os
import sys
import threading
import time
import traceback
import uuid

from functools import wraps
from flask import Blueprint, abort, current_app, request, jsonify
from flask import url_for as _url_for, _request_ctx_stack
from werkzeug.exceptions import HTTPException, InternalServerError

import threaded_logging

logging.basicConfig(format='%(asctime)s | %(name)s | %(message)s',
                    level=logging.DEBUG)


tasks_bp = Blueprint('tasks', __name__)
tasks = {}
tasks_mutex = threading.Lock()
testing = False
data_life_time_sec = 12 * 60 * 60
clean_call_timeout_sec = 60
cleanup_thread = None
stop_cleanup = False


class NoTaskException(Exception):
    """Raised when no task found/detected"""
    pass


class NoThreadException(Exception):
    """Raised when thread cannot be found"""
    pass


class CannotDismissNode(Exception):
    """Raised when node dismiss failed"""
    pass


class StopThread(Exception):
    """Raised when node dismiss failed"""
    pass


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
        This function cleans up old tasks from our in-memory data
        structure and on disk logs.
        """
        global tasks, stop_cleanup
        while not stop_cleanup:
            # Only keep tasks that are running or finished less than
            # data_life_time_sec ago.
            current_time = timestamp()
            tasks_mutex.acquire()
            cleanup_list = [i for i, t in tasks.items()
                            if 'endtime' in t and
                            t['endtime'] > -1 and
                            current_time - t['endtime'] > data_life_time_sec]
            for i in cleanup_list:
                os.remove(tasks.pop(i)['log_file'])
            tasks_mutex.release()
            time.sleep(clean_call_timeout_sec)

    logging.debug('Run cleanup thread')
    cleanup_thread = threading.Thread(target=clean_old_tasks)
    cleanup_thread.start()


def async_task(target_func):
    """
    This decorator transforms a sync route to asynchronous by running it
    in a background thread.
    """
    @wraps(target_func)
    def wrapped(*args, **kwargs):
        def task(app, environ):
            # Create a request context similar to that of the original request
            # so that the task can have access to flask.g, flask.request, etc.
            with app.request_context(environ):
                node_id = request.form['node']
                try:
                    logging.debug('Dismiss node %s' % node_id)
                    try:
                        stop_thread_for_node(node_id)
                    except NoTaskException:
                        logging.debug('Thread for node is not found, continue')
                    except NoThreadException:
                        logging.debug('Node is not found by task, continue')
                    # Run the route function and record the response
                    logging.debug("Executing target function")
                    tasks[task_id]['node'] = node_id
                    tasks[task_id]['os'] = request.form['os']
                    tasks[task_id]['thread_name'] = threading.Thread.getName(
                        threading.current_thread())
                    tasks[task_id]['log_file'] = threaded_logging. \
                        get_log_name(tasks[task_id]['thread_name'])
                    tasks[task_id]['log_handler'] = threaded_logging.start()
                    tasks[task_id]['starttime'] = timestamp()
                    tasks[task_id]['endtime'] = -1
                    tasks[task_id]['started'] = True
                    tasks[task_id]['stopped'] = False
                    tasks[task_id]['rv'] = target_func(*args, **kwargs)
                except HTTPException as e:
                    logging.debug("Caught http exception:" + str(e))
                    tasks[task_id]['rv'] = \
                        current_app.handle_http_exception(e)
                    traceback.print_exc(file=sys.stdout)
                except Exception as e:
                    logging.error("Caught Exception:%s" % sys.exc_info()[1])
                    # The function raised an exception, so we set a 500 error
                    tasks[task_id]['rv'] = InternalServerError()
                    traceback.print_exc(file=sys.stdout)
                except:
                    tasks[task_id]['rv'] = InternalServerError()
                    msg = "Oops in flask_task! %s occured." % sys.exc_info()[1]
                    logging.error(msg)
                finally:
                    # We record the time of the response, to help in garbage
                    # collecting old tasks
                    tasks[task_id]['status'] = 'done'
                    tasks[task_id]['endtime'] = timestamp()
                    threaded_logging.stop(tasks[task_id]['log_handler'])
                    logging.debug("target function completed")
        # Assign an id to the asynchronous task
        task_id = uuid.uuid4().hex

        # Record the task, and then launch it
        tasks_mutex.acquire()
        tasks[task_id] = {'task': threading.Thread(
            target=task, args=(current_app._get_current_object(),
                               request.environ))}
        tasks_mutex.release()
        tasks[task_id]['task'].daemon = True
        tasks[task_id]['task'].start()
        # wait is needed for case when many requests is done
        # and new thread starting took time
        i = 0
        while i < 30:
            i = i + 1
            if 'started' in tasks[task_id]:
                break
            time.sleep(3)
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
                         'Node': task['node'],
                         'OS': task['os'],
                         'stopped': task['stopped'],
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
    for task in tasks.copy():
        # logging.debug(tasks[task])
        # logging.debug(tasks[task]['starttime'])
        t = dict()
        t['start_time'] = tasks[task]['starttime']
        t['end_time'] = tasks[task]['endtime']
        t['node'] = tasks[task]['node']
        t['os'] = tasks[task]['os']
        t['stopped'] = tasks[task]['stopped']
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


@tasks_bp.route('/log/<task_id>', methods=['GET'])
def get_log(task_id):
    task = tasks.get(task_id)
    if task is None:
        abort(404, 'Task "%s" is not found' % task_id)
    logging.debug('Task %s:%s found, loading log' % (task_id, str(task)))
    with open(tasks[task_id]['log_file'], 'r') as file:
        data = file.read()
    return jsonify({'TaskID': task_id, 'LogData': data})


def find_taks_by_node(node_id):
    for t in tasks.copy().keys():
        logging.debug('Check node:' + str(tasks[t]))
        if('node' in tasks[t] and tasks[t]['node'] == node_id and
           'rv' not in tasks[t] and tasks[t]['started'] == True):
            return t
    raise NoTaskException('Cannot find task for "%s" node' % node_id)


def find_thread_by_task(task_id):
    if not(task_id in tasks.keys()):
        raise NoTaskException('No task "%s" found' % task_id)
    for tid, tobj in threading._active.copy().items():
        logging.debug('Check TID %s' % str(tid))
        if tobj is tasks[task_id]['task']:
            logging.debug('Found TID  "%s" for task "%s"' %
                          (str(tid), task_id))
            return tid, tobj
    raise NoThreadException('No thread for task "%s" was found' % task_id)


def stop_thread_for_node(node_id):
    task = find_taks_by_node(node_id)
    thr_id, thr_obj = find_thread_by_task(task)
    logging.debug('Generate StopThread in thread %s' % str(thr_id))
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_long(thr_id), ctypes.py_object(StopThread))
    if res == 0:
        logging.error('Exception raise failure, no target found')
        raise CannotDismissNode('Cannot find thread for raising exception')
    elif res > 1:
        logging.error('Too many thread found')
        raise CannotDismissNode('')
    else:
        tasks[task]['task'].join()
        tasks[task]['stopped'] = True
        logging.debug('Exception raised successfully')
        return task


# node - should be node id in configuration file
@tasks_bp.route('/node/dismiss', methods=['POST'])
def dismiss_node():
    node_id = request.form['node']
    logging.info('Dismissing provision task for node "{}"'.format(node_id))
    # logging.debug(tasks)
    try:
        task = stop_thread_for_node(node_id)
    except CannotDismissNode as cdn_exc:
        msg = 'Caught CannotDismissNode %s' % cdn_exc
        logging.info(msg)
        abort(503, msg)
    except NoTaskException as ntask_exp:
        msg = 'Caught NoTaskException %s' % ntask_exp
        logging.info(msg)
        abort(404, msg)
    except NoThreadException as nthr_exp:
        msg = 'Caught NoThreadException %s' % nthr_exp
        logging.info(msg)
        abort(404, msg)
    except:
        msg = "Oops! In dismiss_node  %s occured." % sys.exc_info()[1]
        logging.error(msg)
        abort(501, msg)

    return jsonify({'stopped_task': task,
                    'node': node_id})
