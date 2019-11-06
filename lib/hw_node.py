
from node import LocalNode
import os
import logging

logging.basicConfig(format='%(asctime)s | %(name)s | %(message)s',
                    level=logging.DEBUG)

conman_server = ''
ipmitool_bin = 'ipmitool'
conman_bin = 'conman'
ipmi_user = ''
ipmi_pass = ''
target_pass =''
roster_file = 'deploy.roster'

def get_ipmi_cycle_cmd(ip, user='', passwd=''):
    if not user:
        user = ipmi_user
    if not passwd:
        user = ipmi_pass

    return "{} -H {} -U {} -P {} -I lanplus power cycle".\
            format(ipmitool_bin, ip, user, passwd)


def get_conman_cmd(server, name):
    return "{} -d {} -j {}".format(conman_bin, server, name)


def power_cycle(node):
    cmd = get_ipmi_cycle_cmd(node['bmc_ip'])
    local = LocalNode()
    local.shell(cmd, trace=True)
    if local.status == 0:
        print("node restarted")
        # TODO check retrun results from results
    else:
        raise Exception(
            "ipmitool call failed with status[{}], stdout [{}], stderr[{}]".
            format(local.status,
                   local.stdout.rstrip(),
                   local.stderr))


# current output after boot
# -----------------------
# Welcome to openSUSE Leap 15.0 - Kernel 4.12.14-lp150.11-default (ttyS1).
#
#
# localhost login
def wait_node_is_ready(node, timeout=5, attempts=120):
    local = LocalNode()
    local.hostname = 'local'
    local.wait_for_port(host=node['ip'], timeout=timeout, attempts=attempts)


def minimal_needed_configuration(node, timeout=60):
    for sls in ["setup_hsm", "configure_services"]:
        local = LocalNode()
        local.hostname = 'local'
        local.pwd()
        local.shell('salt-ssh -i --roster-file ' + roster_file +
                    ' -c .  --no-host-keys --key-deploy --passwd ' +
                     target_pass  +' "' + node['node'] + '" ' +
                    ' state.apply ' + sls + ' -l debug')
        print('Status:', local.status)
        print('Output:', local.stdout.rstrip())
        print('Errors:', local.stderr)
    return local

