import unittest
import shutil
import os
import logging

import pxelinux_cfg
import network_manager
import hw_node

logging.basicConfig(format='%(asctime)s | %(name)s | %(message)s',
                    level=logging.DEBUG)
tftp_cfg_dir = '/tmp/tftp'
pxelinux_cfg_dir = '/tmp/tftp/pxelinux_cfg'


class PxelinuxCfgTest(unittest.TestCase):

    def setUp(self):
        network_manager.data_file = 'test/test_network_cfg.json'

        shutil.rmtree(tftp_cfg_dir, ignore_errors=True)
        os.makedirs(tftp_cfg_dir)

        os.makedirs(pxelinux_cfg_dir, exist_ok=True)
        pxelinux_cfg.tftp_cfg_dir = tftp_cfg_dir
        pxelinux_cfg.default_pxe_server = "1.2.3.4"

        pxelinux_cfg.pxelinux_cfg_dir = pxelinux_cfg_dir
        shutil.rmtree(pxelinux_cfg.pxelinux_cfg_dir, ignore_errors=True)
        os.mkdir(pxelinux_cfg.pxelinux_cfg_dir)

    def tearDown(self):
        shutil.rmtree(tftp_cfg_dir, ignore_errors=True)
        pass

    def test_list_os(self):
        tdir = 'sle-15.1-0.1.1-29.1'
        os.makedirs(tftp_cfg_dir + '/' + tdir)
        found = pxelinux_cfg.get_os_dir(tdir)
        logging.debug("found os directory: " + found)
        self.assertEqual(found, tdir)

        os.symlink(tftp_cfg_dir + '/' + tdir,
                   tftp_cfg_dir + '/sle-15.1')
        found = pxelinux_cfg.get_os_dir('sle-15.1')
        logging.debug("found os directory: " + found)
        self.assertEqual(found, tdir)

    def test_get_boot_record_for_os(self):
        os_id = 'sle-15.1-0.1.1-29.1'
        os.makedirs(tftp_cfg_dir + '/' + os_id)
        boot = pxelinux_cfg.get_boot_record_for_os(
            {'node': 'test_node'}, os_id)
        logging.debug("Boot records: " + boot)
        self.assertRegex(boot,
                         '/minimal-sle-15-sp1.x86_64-0.1.1.xz',
                         'check image')
        self.assertRegex(boot,
                         'http://1.2.3.4/sle-15.1-0.1.1-29.1/', 'check host')
        self.assertRegex(boot,
                         'console=tty1 console=ttyS1,11520', 'check tty')

    def test_prepare_tftp(self):
        tdir = 'sle-15.1-0.1.1-29.1'
        os.makedirs(tftp_cfg_dir + '/' + tdir)
        network_manager.data_file = 'test/test_network_cfg.json'
        node = network_manager.get_node_by_name('test_node')

        mac_file = pxelinux_cfg.get_macfile(node)
        self.assertEqual(mac_file,
                         pxelinux_cfg.pxelinux_cfg_dir +
                         '/01-aa-bb-cc-dd-00-73',
                         'mac file calculation check')

        pxelinux_cfg.set_tftp_dir(node, 'local')
        self.assertTrue(os.path.isfile(mac_file),
                        'local cfg file generated')

        with open(mac_file, 'r') as ifile:
            lines = ifile.readlines()
        cfg = "\n".join(lines)
        self.assertRegex(cfg,
                         r'MENU\s+LABEL\s+Boot\s+local\s+'
                         r'hard\s+drive\s+LOCALBOOT\s-1',
                         'check generated local data #1')
        self.assertRegex(cfg,
                         r'APPEND\s+pxelinux\.cfg\/default',
                         'check generated local data #2')

        pxelinux_cfg.set_tftp_dir(node, 'sle-15.1-0.1.1-29.1')
        self.assertTrue(os.path.isfile(mac_file),
                        'special os cfg file generated')
        with open(mac_file, 'r') as ifile:
            lines = ifile.readlines()
            cfg = "\n".join(lines)

        self.assertRegex(cfg,
                         'KERNEL sle-15.1-0.1.1-29.1/pxeboot.kernel',
                         'check os specific generated data #1')
        self.assertRegex(cfg,
                         'INITRD sle-15.1-0.1.1-29.1/pxeboot.initrd.xz',
                         'check os specific generated data #2')
        self.assertRegex(cfg,
                         r'rd.kiwi.install.pxe\s+rd.kiwi.install.image=',
                         'check os specific generated data #3')

        pxelinux_cfg.cleanup_tftp_dir(node)
        self.assertFalse(os.path.isfile(mac_file),
                         'cfg file removed')

    def test_refresh_symlinks(self):
        os.makedirs(tftp_cfg_dir + '/oem_sle_15sp1-0.1.1')
        logging.debug("Write test file: "
                      + tftp_cfg_dir + '/oem_sle_15sp1-0.1.1/test')
        with open(tftp_cfg_dir + '/oem_sle_15sp1-0.1.1/test', 'w') as ofile:
            ofile.writelines("011")

        pxelinux_cfg.refresh_symlinks('oem_sle_15sp1', '0.1.1')
        logging.debug("Read test file via symlink: "
                      + tftp_cfg_dir + '/oem_sle_15sp1/test')
        with open(tftp_cfg_dir + '/oem_sle_15sp1/test', 'r') as ifile:
            lines = ifile.readlines()

        self.assertFalse(os.path.islink(tftp_cfg_dir + '/oem_sle_15sp1/test'))
        self.assertEqual(lines[0], '011')

        os.makedirs(tftp_cfg_dir + '/oem_sle_15sp1-1.1.1')
        with open(tftp_cfg_dir + '/oem_sle_15sp1-1.1.1/test', 'w') as ofile:
            ofile.writelines("111")

        pxelinux_cfg.refresh_symlinks('oem_sle_15sp1', '1.1.1')
        with open(tftp_cfg_dir + '/oem_sle_15sp1/test', 'r') as ifile:
            lines = ifile.readlines()

        self.assertFalse(os.path.islink(tftp_cfg_dir + '/oem_sle_15sp1/test'))
        self.assertEqual(lines[0], '111')

        logging.debug("---")

    def test_provision_node(self):
        # test awaited open port 22 locally
        # TODO add for case when no ssh port on local port
        # code for open port
        tdir = 'sle-15.1-0.1.1-29.1'
        os.makedirs(tftp_cfg_dir + '/' + tdir)
        os.symlink(tftp_cfg_dir + '/' + tdir,
                   tftp_cfg_dir + '/sle-15.1')
        hw_node.default_cold_restart_timeout = 1
        pxelinux_cfg.default_undoubted_hw_start_timeout = 1
        hw_node.ipmitool_bin = 'echo'
        node = network_manager.get_node_by_name('test_local_node')
        # check provision failure in salt
        hw_node.sls_list = ['setup_hsm']
        with self.assertRaises(Exception):
            pxelinux_cfg.provision_node(node, 'sle-15.1')
        hw_node.sls_list = []
        # provision without failure
        self.assertEqual(
            pxelinux_cfg.provision_node(node, 'sle-15.1'), 1)
        # check provision need reboot
        node['provision_need_reboot'] = 'no'
        self.assertEqual(
            pxelinux_cfg.provision_node(node, 'sle-15.1'), 1)
        node['provision_need_reboot'] = 'yes'
        self.assertEqual(
            pxelinux_cfg.provision_node(node, 'sle-15.1'), 2)


if __name__ == '__main__':
    unittest.main()
