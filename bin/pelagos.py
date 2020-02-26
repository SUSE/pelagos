#!/usr/bin/env python

from flask import Flask, jsonify, abort, request
from flask_tasks import tasks_bp as tasks_blueprint
from flask_tasks import async_task, tasks

import time
import sys
import logging
import getopt
import argparse

import network_manager
import pxelinux_cfg
import hw_node

description = """

REST service which control nodes provisiong via ipmi protocol.
It also do some manipulation with tftp/pxe files

"""
parser = argparse.ArgumentParser(description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter)

parser.add_argument('--config', dest='config', required=True,
                    help='Path to pelagos configuration file')

parser.add_argument('--tftpdir', dest='tftp_dir', required=True,
                    help='tftp root directory')

parser.add_argument('--simulation', dest='simulation', default='',
                    help='Simulation mode, "fast" or "medium" supported now, ' +
                     'used for testing')

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
    if os == pxelinux_cfg.id_local_boot:
        return pxelinux_cfg.id_local_boot
    if os == pxelinux_cfg.id_maintenance_boot:
        return pxelinux_cfg.id_maintenance_boot
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
    sls = ''
    app.logger.info(
        'Provision node [{}]  with OS [{}]'.format(node_id, os))

    if 'extra_sls' in request.form:
        sls = request.form['extra_sls']
        app.logger.info(
            'Additinal salt script[{}]'.format(sls))

    node = _check_input_node(node_id)
    os_id = _check_input_os(os)
    try:
        if app.simulate_mode == 'fast':
            pxelinux_cfg.provision_node_simulate_fast(node,os)
        elif app.simulate_mode == 'medium':
            pxelinux_cfg.provision_node_simulate(node, os)
        else:
            pxelinux_cfg.provision_node(node, os, extra_sls=sls.split())
    except hw_node.TimeoutException as tmt_excp:
        msg_tmt_excp= 'Caught TimeoutException %s' % tmt_excp
        app.logger.info(msg_tmt_excp)
        abort(504, msg_tmt_excp)
    except hw_node.CannotBootException as boot_excp:
        msg_boot_excp = 'Caught CannotBootException %s' % boot_excp
        app.logger.info(msg_boot_excp)
        abort(502, msg_boot_excp)
    except hw_node.BMCException as bmc_excp:
        msg_bmc_excp = 'Caught BMCException %s' % bmc_excp
        app.logger.info(msg_bmc_excp)
        abort(502, msg_bmc_excp)
    except:
        msg = "Oops! %s occured." % sys.exc_info()[1]
        app.logger.info(msg)
        abort(501, msg)
    return jsonify({'status': 'done',
                    'node': node,
                    'os': os_id})


# process command line parameters
def print_help():
    print('pelagos.py -c <config file>')


if __name__ == '__main__':
    args = parser.parse_args()
    network_manager.data_file = args.config
    print("Set configuration file: " + network_manager.data_file)

    pxelinux_cfg.tftp_cfg_dir = args.tftp_dir
    print("Set PXE and TFTP dir to:" + pxelinux_cfg.tftp_cfg_dir)
    pxelinux_cfg.pxelinux_cfg_dir = \
        pxelinux_cfg.tftp_cfg_dir + '/pxelinux.cfg'

    app.simulate_mode=args.simulation
    if app.simulate_mode:
        print("Set simulate mode to :" + app.simulate_mode)
    else:
        print("Set production mode")

    pxelinux_cfg.default_pxe_server  = network_manager.get_option(
        'default_pxe_server')

    hw_node.init()
    pxelinux_cfg.init()

    app.run(debug=True, host='0.0.0.0', threaded=True)
        # False, processes=10)
