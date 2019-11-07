#!/usr/bin/env python
import re
import json
import argparse
import os
import network_manager

description = """ 
Generates configs based on templates for services and pelagos configuration file

for dnsmasq generates a file 
    <target dir>/etc/dnsmasq/dnsmasq.d/network_nodes.conf
with records like this
 
    ...
    dhcp-host=aa:bb:cc:dd:68:7c,ses-client-3,1.2.3.13
    ...
    ptr-record=13.3.2.1.in-addr.arpa,ses-client-3.a.b.de
    ...

for conman generates file <target dir>/states/etc/conman.conf  based on 
template  <target dir>states/etc/conman.conf.tmpl with records like this

    CONSOLE name="ses-client-3" IPMIOPTS="U:<user>,P:<pass>" dev="ipmi:<ipmi server>"

for salt generates roster file <target dir>/deploy.roster

    ses-client-3.a.b.de:
      host: 1.2.3.13
      user: root

for teuthology generates sql script <target dir>/sql/nodes.sql

    INSERT INTO nodes (name, machine_type, mac_address, is_vm, locked, arch, description)
        VALUES  ( 'ses-client-3.a.b.de' , 'client' ,
            'aa:bb:cc:dd:67:16' , 'f' , 'f' , 'x86-64' , '' ) ;
"""

parser = argparse.ArgumentParser(description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter)


def reverse_ip(ip):
    ip_split = re.search('(\d+)\.(\d+)\.(\d+)\.(\d+)', ip)
    print("ip_split:")
    print(ip_split.groups())
    return ip_split.groups()[3] + '.'\
           + ip_split.groups()[2] + '.'\
           + ip_split.groups()[1] + '.'\
           + ip_split.groups()[0]

# get host name from probably fqdn
def hn(name):
    return name.split('.')[0]


# hardcoded but should be parametrized
pxe_output_file = 'states/etc/dnsmasq/dnsmasq.d/network_nodes.conf'
conman_tmpl = "states/etc/conman.conf.tmpl"
conman_cfg = "states/etc/conman.conf"
roster_file = "deploy.roster"

bmc_user = ""
bmc_pass = ""
domain = ""

sql_script_file = 'sql/nodes.sql'
sql_line_prefix = 'INSERT INTO nodes ' \
                  '(name, machine_type, mac_address, is_vm, ' \
                  'locked, arch, description) VALUES '

parser.add_argument('-c', dest='config_file', required=True,
                    help='path to configuration file')

parser.add_argument('-d', dest='target_dir', required=True,
                    help='target directrory for generating files')

args = parser.parse_args()

network_manager.data_file = args.config_file
nodes = network_manager.get_nodes()

target_dir_prefix = args.target_dir + "/"

bmc_user = network_manager.get_option('ipmi_user')
bmc_pass = network_manager.get_option('ipmi_pass')
domain = network_manager.get_option('domain')


consoles = ""
roster_recors = ""
# ----------- iterating and preparing data ---------------
pxe_node_lines = []
pxe_node_ptr_lines = []
nodes_sql_lines = []

for n in nodes:
    print('Process node' + n['node'])
    
    if n['ip_type'] == 'dynamic':
        pxe_node_lines.append("dhcp-host={},{},{}"
                          .format(n['mac'], hn(n['node']), n['ip']))
        pxe_node_ptr_lines.append("ptr-record={}.in-addr.arpa,{}.{}"
                              .format(reverse_ip(n['ip']),
                                      hn(n['node']),
                                      domain))

    if n['bmc_ip_type'] == 'dynamic':
        pxe_node_lines.append("dhcp-host={},{}-bmc,{}"
                          .format(n['bmc_mac'], hn(n['node']), n['bmc_ip']))
        pxe_node_ptr_lines.append("ptr-record={}.in-addr.arpa,{}-bmc.{}"
                              .format(reverse_ip(n['bmc_ip']),
                                      hn(n['node']),
                                      domain
                                      ))

    if ('hsm_ip_type' in n.keys()) and (n['hsm_ip_type'] == 'dynamic'):
        pxe_node_lines.append("dhcp-host={},{}-hsm,{}"
                          .format(n['hsm_mac'], hn(n['node']), n['hsm_ip']))
        pxe_node_ptr_lines.append("ptr-record={}.in-addr.arpa,{}-hsm"
                              .format(reverse_ip(n['hsm_ip']), hn(n['node'])))

    consoles = consoles +\
               "\nCONSOLE name=\"{}\" IPMIOPTS=\"U:{},P:{}\" dev=\"ipmi:{}\""\
                   .format(hn(n['node']), bmc_user, bmc_pass, n['bmc_ip'])
    roster_recors = roster_recors +\
                    n['node']+":\n" +\
                    "  host: " + n['ip'] + "\n" +\
                    "  user: root\n"
    if 't_exclude' in n.keys() and n['t_exclude'] != 'yes':
        sql_update_body = [
                "'" + n['node'] + "'",
                "'" + n['t_machine_type'] + "'",
                "'" + n['mac'] + "'",
                "'f'",
                "'f'",
                "'x86-64'",
                "'" + n['comment'] + "'",
            ]
        nodes_sql_lines.append(
            sql_line_prefix +\
            " ( " + " , ".join(sql_update_body) + " ) ;\n"
            #+\
            #" WHERE name     = '" + n['node'] + "' ;\n"
        )

# ----------- pxe ---------------
with open(target_dir_prefix + pxe_output_file, 'w') as ofile:
    ofile.write("\n".join(pxe_node_lines)+"\n")    
    ofile.write("\n".join(pxe_node_ptr_lines)+"\n")
print("File [{}] written".format(target_dir_prefix +
                                    pxe_output_file))

# ----------- conman ---------------
lines = ""
with open(target_dir_prefix + conman_tmpl, "r") as cf:
    for line in cf:
        line = line.replace("@@CONSOLES@@", consoles)
        lines = lines + line

with open(target_dir_prefix + conman_cfg, 'w') as ofile:
    ofile.write(lines)
print("File [{}] written".format(target_dir_prefix + conman_cfg))

# ----------- roster ---------------

with open(target_dir_prefix + roster_file, 'w') as ofile:
    ofile.write(roster_recors)
print("File [{}] written".format(target_dir_prefix + roster_file))

# ----------- sql file ---------------

with open(target_dir_prefix + sql_script_file, 'w') as ofile:
    ofile.write("".join(nodes_sql_lines))
print("File [{}] written".format(target_dir_prefix +
                                     sql_script_file))

