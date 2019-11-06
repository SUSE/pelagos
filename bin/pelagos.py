#!/usr/bin/env python

from flask import Flask, jsonify, abort, request
from flask_tasks import tasks_bp as tasks_blueprint
from flask_tasks import async_task, tasks

import time
import sys
import logging
import getopt

import network_manager
import pxelinux_cfg
import hw_node


logging.basicConfig(format='%(asctime)s | %(name)s | %(message)s',
                    level=logging.DEBUG)

app = Flask('pelagos')

# Register async tasks support
app.register_blueprint(tasks_blueprint, url_prefix='/tasks')
app.ver_name='pelagos'
app.version = '0.0.3'
app.simulate_mode = ''


def _check_input_node(node_id):
    app.logger.info('Searching node [%s]', node_id)
    node = network_manager.get_node_by_name(node_id, exception=False)
    if not len(node):
        app.logger.info('Failed to find node {}'.format(node_id))
        abort(404, "No node [{}] found".format(node_id))
    return node


def _check_input_os(os):
    if not len(os):
        abort(404, "No OS string [{}] found".format(os))
    if os == 'local':
        return pxelinux_cfg.id_local_boot
    # list tftp dir and find all dirs, compare it with
    # required os and do fuzzy selection
    app.logger.info('Searching os  %s on disk', os)
    checked_os = pxelinux_cfg.get_os_dir(os)
    if checked_os == '':
        app.logger.info('Failed to find os %s', os)
        abort(404, "No os image [{}] found in dir [{}]".
              format(os, pxelinux_cfg.tftp_cfg_dir))
    app.logger.info('Found os [%s]', checked_os)
    return checked_os


@app.route('/')
def index():
    return "Network controller service\n" \
           "use http://<host>:<port>/pxe/api/tasks\n" \
           "for access to REST functionality\n"


@app.route('/version', methods=['GET'])
def get_version():
    app.logger.info('Return version')
    return jsonify({'app': app.ver_name,
                    'version': app.version})


@app.route('/nodes', methods=['GET'])
def get_nodes():
    app.logger.info('Get all nodes information')
    nodes = network_manager.get_nodes()
    return jsonify(
        {'nodes': nodes,
            'pxe': pxelinux_cfg.get_pxe_map(nodes)})


@app.route('/node/<string:node_id>', methods=['GET'])
def get_node(node_id):
    node = _check_input_node(node_id)
    os = pxelinux_cfg.get_configured_os(node)
    return jsonify({'node': node,
                    'pxe': {'os': os,
                            'pxe_file': pxelinux_cfg.get_macfile(node)}})


@app.route('/check_image/<string:os>', methods=['GET'])
def check_image(os):
    os_id = _check_input_os(os)
    return jsonify({'os': os_id})

#
# @app.route('/node/refresh_menu', methods=['GET'])
# def refresh_menu():
#    app.logger.info('Refresh menu. TBI')

# PUT
@app.route('/node/bootrecord/<string:node_id>/<string:os>', methods=['GET'])
def bootrecord_node(node_id, os):
    app.logger.info('Set boot record for node {}  with OS {}'.format(node_id, os))
    node = _check_input_node(node_id)
    os_id = _check_input_os(os)
    pxelinux_cfg.set_tftp_dir(node, os_id)
    return jsonify({'status': 'single boot record set',
                    'node': node,
                    'os': os_id
                    })

# DEL
@app.route('/node/rmbootrecord/<string:node_id>', methods=['GET'])
def rmbootrecord_node(node_id):
    app.logger.info('Remove boot record for node {}'.format(node_id))
    node = _check_input_node(node_id)
    pxelinux_cfg.cleanup_tftp_dir(node)
    return jsonify({'status': 'dedicated boot record removed',
                    'node': node
                    })

#PATCH
# os - PATCH parameter
# node_id - parameter from url
@app.route('/node/provision', methods=['POST'])
@async_task
def provision_node():
    if request.method != 'POST':
        return abort(405, "Use POST method")
    # time.sleep(30)
    app.logger.info("Data for provision: [" + str(request.get_data(as_text=True)) + "]")
    os = request.form['os']
    node_id = request.form['node']
    app.logger.info(
        'Provision node [{}]  with OS [{}]'.format(node_id, os))
    node = _check_input_node(node_id)
    os_id = _check_input_os(os)
    if app.simulate_mode == 'fast':
        pxelinux_cfg.provision_node_simulate_fast(node,os)
    elif app.simulate_mode == 'medium':
        pxelinux_cfg.provision_node_simulate(node, os)
    else:
        pxelinux_cfg.provision_node(node, os)
    return jsonify({'status': 'done',
                    'node': node,
                    'os': os_id})


# process command line parameters
def print_help():
    print('pelagos.py -c <config file>')


if __name__ == '__main__':
    try:

        opts, args = getopt.getopt(sys.argv[1:],
                                   "hc:",
                                   ["config=",
                                    "simulate=",
                                    "tftp-dir="])
    except getopt.GetoptError:
        print('Parameters parsing error!')
        print_help()
        sys.exit(2)

    if len(opts) == 0:
        print('No parameters set!')
        print_help()
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print_help()
            sys.exit()
        elif opt in ("-c", "--config"):
            #TODO make it obligatory
            print("Set configuration file: " + arg)
            network_manager.data_file = arg
        elif opt in ("--simulate"):
            print("Set simulate mode to :" + arg)
            app.simulate_mode=arg
        elif opt in ("--tftp-dir"):
            print("Set PXE and TFTP dir to:" + arg)
            pxelinux_cfg.tftp_cfg_dir = arg
            pxelinux_cfg.pxelinux_cfg_dir = \
                pxelinux_cfg.tftp_cfg_dir + '/pxelinux.cfg'

    pxelinux_cfg.default_pxe_server  = network_manager.get_option(
        'default_pxe_server')    
    hw_node.ipmi_user = network_manager.get_option('ipmi_user')
    hw_node.ipmi_pass = network_manager.get_option('ipmi_pass')
    hw_node.target_pass = network_manager.get_option(
        'target_node_password')

    app.run(debug=True, host='0.0.0.0', threaded=True)
        # False, processes=10)
