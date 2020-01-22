import os
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

#tftp_dir= '/srv/tftpboot/pxelinux.cfg'
tftp_cfg_dir = '/srv/tftpboot'
pxelinux_cfg_dir = tftp_cfg_dir + '/pxelinux.cfg'
default_pxe_server = ''
maintenance_image_kernel = ''
maintenance_image_initrd = ''

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
  KERNEL {}/pxeboot.kernel
  INITRD {}/pxeboot.initrd.xz
  APPEND  biosdevname=0 net.ifnames=0  rd.kiwi.install.pxe rd.kiwi.install.image=http://{}/{}/{}.xz console=tty1 console=ttyS1,115200 kiwidebug=1
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
        image = re.compile('^oem-').sub('', os_id)
        image = re.compile('-\d+\.\d+\.\d+').sub('', image)
        cfg = pxe_common_os_boot_tmpl.format(
                            os_id, os_id,
                            default_pxe_server, os_id, image)
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

#def get_configuration(image='opensuse-leap-15.0.xz', pxe_server=default_pxe_server):
#    tmpl = pxe_common_settings + pxe_local_boot
#    #.format(pxe_server, image)
#    return tmpl


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


def get_os_dir(os_str):
    result = ''
    logging.debug("Search [{}] in dir[{}]".format(os_str, tftp_cfg_dir))
    for dirname, dirnames, filenames in os.walk(tftp_cfg_dir):
        logging.debug("Check dir [{}]".format(dirname))
        # os_match = re.search(r'(oem-.+-\d+\.\d+\.\d+)$', dirname)
        # os_match = re.search(r'(oem-.+-\d+\.\d+\.\d+)$', dirname)
        #os_match = re.search(r'/(.+-\d+\.\d+\.\d+)$', dirname)
        #dirname. os.path.basename(dirname)
        #if os_match is not None:
        #    logging.debug('Found dir [{}], check it '.
        #                  format(str(os_match.groups())))
        if os.path.basename(dirname).startswith(os_str):
            logging.debug('Found, set it')
            if os.path.basename(dirname) > result:
                result = os.path.basename(dirname)

    return result


def refresh_symlinks(os_id, ver):
    if os.path.islink(tftp_cfg_dir + '/' + os_id):
        logging.debug('Symlink found, remove it')
        os.remove(tftp_cfg_dir + '/' + os_id)
    logging.debug("Create symlink")
    os.symlink(tftp_cfg_dir + '/' + os_id + '-' + ver,
               tftp_cfg_dir + '/' + os_id, True)


def refresh_mainmenu():
    disto_list = []
    for name in os.listdir(tftp_cfg_dir):
        if name not in (os.curdir, os.pardir):
            full = os.path.join(tftp_cfg_dir, name)
            if os.path.islink(full):
                logging.debug(name + '->' + os.readlink(full))
                disto_list.append(name)
    cfg_file = pxelinux_cfg_dir + '/default'
    if os.path.isfile(cfg_file):
        os.rename(cfg_file, cfg_file+"."+time.gmtime())
    disto_menu = ''
    # os_image_dir, os_image_dir, pxe_server, os_image_dir, os_image_dir
    for disto in disto_list:
        os_image_dir = tftp_cfg_dir + "/" + disto
        image = re.compile(r'^oem-').sub('', os_image_dir)
        image = re.compile(r'-\d+\.\d+\.\d+').sub('', image)
        disto_menu = disto_menu + pxe_common_os_boot_tmpl.format(
            os_image_dir, os_image_dir, default_pxe_server,
            os_image_dir, image)

    logging.debug("Write new pxe configuration: " + cfg_file)
    with open(cfg_file, 'w') as ofile:
        ofile.writelines(pxe_common_settings +
                         pxe_main_menu.format(
                             maintenance_image_kernel,
                             maintenance_image_initrd,
                             default_pxe_server) +
                         disto_menu)

def provision_node_simulate_fast(node, os_id):
    logging.debug("********************** simulating fast provisioning ******************************")
    time.sleep(3)
    return 1

def provision_node_simulate(node, os_id):
    logging.debug("********************** simulating 20 sec provisioning ******************************")
    time.sleep(20)
    return 1

def provision_node(node, os_id):
    set_tftp_dir(node, os_id)
    hw_node.power_cycle(node)
    time.sleep(30)
    hw_node.wait_node_is_ready(node)
    hw_node.minimal_needed_configuration(node)
    # #pxelinux_cfg.cleanup_tftp_dir(node)
    set_tftp_dir(node, id_local_boot)
    return 1
