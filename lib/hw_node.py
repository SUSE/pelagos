
from node import LocalNode
import logging
import network_manager
import re
import sys
import time

conman_server = ''
ipmitool_bin = 'ipmitool'
conman_log_prefix = '/var/log/conman/console.'
conman_bin = 'conman'
ipmi_user = ''
ipmi_pass = ''
target_pass = ''
roster_file = 'deploy.roster'
salt_cfg_dir = '.'
sls_list = []
default_port_lookup_timeout = 5
default_port_lookup_attempts = 6
default_conman_line_max_age = 700
default_cold_restart_timeout = 30


class TimeoutException(Exception):
    """Raised when node cannot be achieve in time"""
    pass


class CannotBootException(Exception):
    """Raised when node conman log freeze in middle of boot"""
    pass


class BMCException(Exception):
    """Raised when BMC operation failed"""
    pass


def init():
    global ipmi_user
    ipmi_user = network_manager.get_option('ipmi_user')
    global ipmi_pass
    ipmi_pass = network_manager.get_option('ipmi_pass')
    global target_pass
    target_pass = network_manager.get_option(
        'target_node_password')

    if network_manager.get_option('roster_file'):
        global roster_file
        roster_file = network_manager.get_option(
            'roster_file', roster_file)

    if network_manager.get_option('salt_cfg_dir'):
        global salt_cfg_dir
        salt_cfg_dir = network_manager.get_option(
            'salt_cfg_dir', salt_cfg_dir)

    if network_manager.get_option('sls_list'):
        global sls_list
        sls_list = [x.strip() for x in
                    network_manager.get_option('sls_list').split(',')]


def get_ipmi_cmd(ip, cmd='power cycle', user=None, passwd=None):
    if not user:
        user = ipmi_user
    if not passwd:
        passwd = ipmi_pass

    return "{} -H {} -U {} -P {} -I lanplus {}".\
        format(ipmitool_bin, ip, user, passwd, cmd)


def get_conman_cmd(server, name):
    return "{} -d {} -j {}".format(conman_bin, server, name)


def get_salt_cmd(sls, node):
    return 'salt-ssh -i --roster-file ' + roster_file +\
                    ' -c ' + salt_cfg_dir +\
                    ' --no-host-keys --key-deploy' +\
                    ' --passwd ' + target_pass +\
                    ' "' + node + '" ' +\
                    ' state.apply ' + sls + ' -l debug'


def exec_bmc_command(node, ipmi_command):
    cmd = get_ipmi_cmd(node['bmc_ip'], ipmi_command)
    local = LocalNode()
    try:
        logging.debug('Execute command: ' + cmd)
        local.shell(cmd, trace=True)
    except:
        BMCException(sys.exc_info()[1])
    logging.debug('Status:' + str(local.status))
    logging.debug('Output:' + local.stdout.rstrip())
    logging.debug('Errors:' + local.stderr)
    if local.status == 0:
        logging.debug("Command '%s' executed successfully" % cmd)
        # TODO check retrun results from results
    else:
        logging.debug("Command '%s' failed, raise exception" % cmd)
        raise BMCException(
            "ipmitool call failed with status[{}], stdout [{}], stderr[{}]".
            format(local.status,
                   local.stdout.rstrip(),
                   local.stderr))


def last_nonempty_line(filepath):
    """Return last non empty and not auxillary conman line
        filepath: path to file for finding last line
        Function is using some magic string which are defined
        in conman.
    """
    tail = LocalNode()
    tail.shell('tail -n 100 ' + filepath,
               stop=True, quiet=True, die=False)
    for str in reversed(tail.stdout.rstrip().splitlines()):
        if str == '' or \
            str.startswith('<ConMan> Console') or \
           re.search(r'\d\d\d\d-\d\d-\d\d\s+\d\d:\d\d:\d\d\s*$', str):
            continue
        else:
            return str

    return 'no_meaningful_line_found'


def get_provision_ip(node):
    host = node['ip']
    logging.debug('node = ' + str(node))
    if 'boot_ip' in node:
        host = node['boot_ip']
    return host


def wait_node_is_ready(node,
                       timeout=900,
                       conman_line_max_age=None,
                       max_cold_restart=3,
                       port_lookup=22,
                       port_lookup_timeout=None,
                       port_lookup_attempts=None):
    """ Return true if node(and ssh) start in time
        Raise exceptions in other cases

        Parameters:
        timeout: overall timeout for boot and start ssh
            (ssh starts after end of kiwi provisioning)
        conman_line_max_age: how long last conman line
            coud be not changed (mean node stuck)
        max_cold_restart: maximum nuber of cold restarts

    """
    if port_lookup_timeout is None:
        port_lookup_timeout = default_port_lookup_timeout
    if port_lookup_attempts is None:
        port_lookup_attempts = default_port_lookup_attempts
    if conman_line_max_age is None:
        conman_line_max_age = default_conman_line_max_age

    starttime = time.time()
    conman_line = 'start_line'
    conman_line_time = time.time()
    conmanfile = conman_log_prefix + node['node'].split('.')[0]
    cold_restart_count = 0

    while starttime+timeout > time.time():

        # check last line in conman log
        new_conman_line = last_nonempty_line(conmanfile)
        if conman_line != new_conman_line:
            # logging.debug("New log detected:"+new_conman_line)
            conman_line = new_conman_line
            conman_line_time = time.time()
        if (time.time() - conman_line_time) > conman_line_max_age:
            logging.info("Node boot failure detected, make cold restart")
            exec_bmc_command(node, 'power off')
            time.sleep(default_cold_restart_timeout)
            exec_bmc_command(node, 'power on')
            if cold_restart_count >= max_cold_restart:
                logging.error('Achieved max cold restart couter ' +
                              '%s for node %s,throws exception'
                              % (max_cold_restart, node['node']))
                raise CannotBootException(
                    "max cold restart couter (%s) for %s" %
                    (max_cold_restart, node['node']))
            cold_restart_count += 1
            conman_line_time = time.time()
            next

        # check port status
        try:
            logging.debug("timeout=" + str(port_lookup_timeout))
            local = LocalNode()
            local.wait_for_port(host=get_provision_ip(node),
                                port=port_lookup,
                                timeout=port_lookup_timeout,
                                attempts=port_lookup_attempts)
            logging.debug("Connected to node %s " % node['node'])
            return True
        except:
            logging.debug("Node {} have not started in timeout {}".format(
                get_provision_ip(node), port_lookup_timeout))

    raise TimeoutException("{} have not started in timeout {}".format(
        get_provision_ip(node), timeout))


def minimal_needed_configuration(node, timeout=60, extra_sls=[]):
    full_sls = sls_list + extra_sls
    logging.debug('Executing salt script[{}]'.format(full_sls))
    for sls in full_sls:
        local = LocalNode()
        local.pwd()
        try:
            local.shell(get_salt_cmd(sls, get_provision_ip(node)))
        except:
            raise Exception('Salt execution failed: ' + sys.exc_info()[1])
        finally:
            logging.debug('Salt Status:' + str(local.status))
            logging.debug('Satl Output:' + local.stdout.rstrip())
            logging.debug('Salt Errors:' + local.stderr)
    logging.debug('Executed salt script[{}]'.format(full_sls))
