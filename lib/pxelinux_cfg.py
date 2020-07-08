import os
import os.path
import re
import logging
import time
import hw_node
import network_manager

# https://wiki.syslinux.org/wiki/index.php?title=PXELINUX
# use mac address for now
# /srv/tftp/pxelinux.cfg/01-88-99-aa-bb-cc-dd
#

id_local_boot = 'local'
id_maintenance_boot = 'maintenance_image'
wait_node_is_ready_timeout = 900
default_undoubted_hw_start_timeout = 30
tftp_cfg_dir = '/srv/tftpboot'
pxelinux_cfg_dir = tftp_cfg_dir + '/pxelinux.cfg'
default_pxe_server = ''
maintenance_image_kernel = ''
maintenance_image_initrd = ''

pxe_debug_opts = 'rd.debug rd.kiwi.debug'
pxe_console_opts = 'console=tty1 console=ttyS1,115200'
pxe_bios_opts = 'biosdevname=0 net.ifnames=0'


pxe_common_settings = '''

DEFAULT menu.c32
PROMPT 0
TIMEOUT 100
MENU TIMEOUTROW 20

'''

pxe_main_menu = '''

LABEL maintenance_image
  MENU DEFAULT
  KERNEL boot/{}
  INITRD boot/{}
  APPEND console=tty1 console=ttyS1,115200 kiwiserver={}  ramdisk_size=2048000 disableProgressInfo=1 kiwidebug=1
  MENU DEFAULT


LABEL memtest86
  MENU LABEL Memtest86+ 5.01
  KERNEL /boot/memtest86+-5.01

'''

pxe_local_boot = '''

LABEL local
  MENU LABEL Boot local hard drive
  LOCALBOOT -1
  MENU DEFAULT

'''

pxe_main_menu_submenu = '''

LABEL mainmenu
  MENU LABEL Main Menu
  KERNEL menu.c32
  APPEND pxelinux.cfg/default

'''

# tmpl parameters
# os_image_dir, os_image_dir, pxe_server, os_image_dir, os_image_dir
pxe_common_os_boot_tmpl = '''

LABEL oem linux
  KERNEL {os}/pxeboot.kernel
  INITRD {os}/pxeboot.initrd.xz
  APPEND {bios} rd.kiwi.install.pxe rd.kiwi.install.image=http://{server}/{dir}/{image} {tty} {debug}
  MENU DEFAULT

'''

const_default_pxe = 'Default config is used: pxelinux.cfg/default'
const_dedicated_pxe = 'Dedicated undefined config is used'


def init():
    global maintenance_image_kernel
    if network_manager.get_option('maintenance_image_kernel'):
        maintenance_image_kernel = \
            network_manager.get_option('maintenance_image_kernel')

    global maintenance_image_initrd
    if network_manager.get_option('maintenance_image_initrd'):
        maintenance_image_initrd = \
            network_manager.get_option('maintenance_image_initrd')


def get_pxe_map(nodes):
    oses = {}
    for node in nodes:
        os = get_configured_os(node)
        oses[node['node']] = {'os': os,
                              'pxe_file': get_macfile(node)}
    logging.debug(oses)
    return oses


def get_macfile(node):
    mac = (node['mac']).replace(':', '-').lower()
    return pxelinux_cfg_dir + '/01-' + mac


def get_boot_record_for_os(node, os_id):
    if os_id == id_local_boot:
        cfg = pxe_local_boot
    elif os_id == id_maintenance_boot:
        cfg = pxe_main_menu.format(
                             maintenance_image_kernel,
                             maintenance_image_initrd,
                             default_pxe_server)
    else:
        image = ''
        # split str same as 'sle-15.1-0.1.1-29.1' to version
        print('****************************')
        print(get_os_dir(os_id))
        print('----------------------------')
        version = \
            re.search(r'(\w+)\-(\d+)\.(\d+)\-(\d+\.\d+\.\d+)\-(\d+\.\d+)',
                      get_os_dir(os_id))
        if version:
            image = "minimal-%s-%s-sp%s.x86_64-%s.xz" % (
                    version.group(1),
                    version.group(2),
                    version.group(3),
                    version.group(4)
                    )
        cfg = pxe_common_os_boot_tmpl.format(
                            os=os_id,
                            server=default_pxe_server,
                            dir=os_id,
                            image=image,
                            bios=pxe_bios_opts,
                            debug=pxe_debug_opts,
                            tty=pxe_console_opts)
    return "# os={}\n".format(os_id) + \
           "# node={}\n".format(node['node']) + \
           pxe_common_settings + cfg + pxe_main_menu_submenu


def get_configured_os(node):
    logging.debug("node = {}".format(node))
    logging.debug("Get mapping for node {}".format(node['node']))
    pxe_file = get_macfile(node)
    if os.path.isfile(get_macfile(node)):
        with open(pxe_file, 'r') as ifile:
            pxe_file_data = ifile.readlines()
        os_match = re.search('os=(.*)\s', "".join(pxe_file_data))
        if os_match:
            logging.debug("os_match=")
            logging.debug(os_match.groups()[0])
            return os_match.groups()[0]
        else:
            return const_dedicated_pxe
    else:
        return const_default_pxe


def set_tftp_dir(node, os_id):
    cfgdata = get_boot_record_for_os(node, os_id)
    # get_configuration(os_id)
    logging.debug("get_configuration:" + cfgdata)

    with open(get_macfile(node), 'w') as ofile:
        ofile.writelines(cfgdata)

    logging.info("prepared tftp layout for node[{}] with file [{}]".format(
        node['node'], get_macfile(node)
    ))


def cleanup_tftp_dir(node):
    os.remove(get_macfile(node))


def get_os_dir(os_rel_path):
    logging.debug("Search [{}] in dir[{}]".format(os_rel_path, tftp_cfg_dir))
    abs_os_path = "%s/%s" % (tftp_cfg_dir, os_rel_path)

    # for teuthology we use symlink to actual kiwi build
    if os.path.islink(abs_os_path):
        real_path = os.readlink(abs_os_path)
        return os.path.basename(real_path)
    elif os.path.exists(abs_os_path):
        return os_rel_path

    return None


def refresh_symlinks(os_id, ver):
    if os.path.islink(tftp_cfg_dir + '/' + os_id):
        logging.debug('Symlink found, remove it')
        os.remove(tftp_cfg_dir + '/' + os_id)
    logging.debug("Create symlink")
    os.symlink(tftp_cfg_dir + '/' + os_id + '-' + ver,
               tftp_cfg_dir + '/' + os_id, True)


def provision_node_simulate_fast(node, os_id):
    logging.debug("********************** simulating fast provisioning")
    time.sleep(3)
    return 1


def provision_node_simulate(node, os_id):
    logging.debug("********************** simulating 20 sec provisioning")
    time.sleep(20)
    return 1


def provision_node_simulate_failure(node, os_id):
    logging.debug("********************** simulating provisioning timeout")
    # timeout is needed for avoid race condition in thread start
    time.sleep(2)
    raise TimeoutException("A node have not started in timeout (test mode)")


def provision_node(node, os_id, extra_sls=[]):
    set_tftp_dir(node, os_id)
    hw_node.exec_bmc_command(node, 'power cycle')
    time.sleep(default_undoubted_hw_start_timeout)
    hw_node.wait_node_is_ready(node, timeout=wait_node_is_ready_timeout)
    set_tftp_dir(node, id_local_boot)
    if not (os_id == id_local_boot or
            os_id == id_maintenance_boot):
        hw_node.minimal_needed_configuration(node, extra_sls=extra_sls)
    if ('provision_need_reboot' in node.keys() and
            node['provision_need_reboot'] == 'yes'):
        hw_node.exec_bmc_command(node, 'power cycle')
        time.sleep(default_undoubted_hw_start_timeout)
        hw_node.wait_node_is_ready(
            node, timeout=wait_node_is_ready_timeout)
        return 2
    return 1
