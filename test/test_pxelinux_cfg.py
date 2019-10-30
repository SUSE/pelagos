import unittest
import shutil
import os
import logging

import pxelinux_cfg
import network_manager

logging.basicConfig(format='%(asctime)s | %(name)s | %(message)s',
                    level=logging.DEBUG)
tftp_cfg_dir = '/tmp/tftp'
pxelinux_cfg_dir = "/tmp/tftp/pxelinux_cfg"

class PxelinuxCfgTest(unittest.TestCase):

    def setUp(self):
        network_manager.data_file = 'test/test_network_cfg.json'

        shutil.rmtree(tftp_cfg_dir, ignore_errors=True)
        os.makedirs(tftp_cfg_dir, exist_ok=True)
        os.makedirs(pxelinux_cfg_dir, exist_ok=True)
        pxelinux_cfg.tftp_cfg_dir = tftp_cfg_dir

        pxelinux_cfg.pxelinux_cfg_dir = pxelinux_cfg_dir
        shutil.rmtree(pxelinux_cfg.pxelinux_cfg_dir, ignore_errors=True)
        os.mkdir(pxelinux_cfg.pxelinux_cfg_dir)

    def tearDown(self):
        shutil.rmtree(tftp_cfg_dir, ignore_errors=True)

    def test_list_os(self):
        os.makedirs(tftp_cfg_dir + '/oem-sle_15sp1')

        os.makedirs(tftp_cfg_dir + '/oem-sle_15sp1-0.0.1')
        found = pxelinux_cfg.get_os_dir('oem-sle_15sp1')
        logging.debug("found os directory: " + found)
        self.assertEqual(found, 'oem-sle_15sp1-0.0.1')

        os.makedirs(tftp_cfg_dir + '/oem-sle_15sp1-0.0.3')
        found = pxelinux_cfg.get_os_dir('oem-sle_15sp1')
        logging.debug("found os directory: " + found)
        self.assertEqual(found, 'oem-sle_15sp1-0.0.3')

        os.makedirs(tftp_cfg_dir + '/oem-sle_15sp1-1.0.1')
        found = pxelinux_cfg.get_os_dir('oem-sle_15sp1')
        logging.debug("found os directory: " + found)
        self.assertEqual(found, 'oem-sle_15sp1-1.0.1')

        os.makedirs(tftp_cfg_dir + '/oem-sle-15.1-1.0.5')
        found = pxelinux_cfg.get_os_dir('oem-sle-15.1')
        logging.debug("found os directory: " + found)
        self.assertEqual(found, 'oem-sle-15.1-1.0.5')

        found = pxelinux_cfg.get_os_dir('ubuntu-18.04')
        logging.debug("found os directory: " + found)
        self.assertEqual(found, '')

    def test_prepare_tftp(self):
        network_manager.data_file = 'test/test_network_cfg.json'
        node = network_manager.get_node_by_name('test_node')

        mac_file = pxelinux_cfg.get_macfile(node)
        self.assertEqual(mac_file,
                         pxelinux_cfg.pxelinux_cfg_dir +
                         '/01-ac-1f-6b-70-68-73',
                         'mac file calculation check')

        pxelinux_cfg.set_tftp_dir(node, 'local')
        self.assertTrue(os.path.isfile(mac_file),
                        'local cfg file generated')

        with open(mac_file, 'r') as ifile:
            lines = ifile.readlines()
        cfg = "\n".join(lines)
        self.assertRegex(cfg,
                         'MENU\s+LABEL\s+Boot\s+local\s+'
                         'hard\s+drive\s+LOCALBOOT\s-1',
                         'check generated local data #1')
        self.assertRegex(cfg,
                         'APPEND\s+pxelinux\.cfg\/default',
                         'check generated local data #2')

        pxelinux_cfg.set_tftp_dir(node, 'oem-sle_15sp1')
        self.assertTrue(os.path.isfile(mac_file),
                        'special os cfg file generated')
        with open(mac_file, 'r') as ifile:
            lines = ifile.readlines()
            cfg = "\n".join(lines)

        self.assertRegex(cfg,
                         'KERNEL oem-sle_15sp1/pxeboot.kernel',
                         'check os specific generated data #1')
        self.assertRegex(cfg,
                         'INITRD oem-sle_15sp1/pxeboot.initrd.xz',
                         'check os specific generated data #2')
        self.assertRegex(cfg,
                         'rd.kiwi.install.pxe\s+rd.kiwi.install.image='
                         'http://10.162.230.2/oem-sle_15sp1/'
                         'sle_15sp1.xz\s+console=tty1',
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
        with open(tftp_cfg_dir + '/oem_sle_15sp1/test','r') as ifile:
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


    def test_refresh_mainmenu(self):

        os.makedirs(tftp_cfg_dir + '/oem_sle_15sp1-0.1.1')
        pxelinux_cfg.refresh_symlinks('oem_sle_15sp1', '0.1.1')

        os.makedirs(tftp_cfg_dir + '/oem_sle_12sp4-0.0.1')
        pxelinux_cfg.refresh_symlinks('oem_sle_12sp4', '0.0.1')

        os.makedirs(tftp_cfg_dir + '/oem_sle_15sp1-1.1.1')

        pxelinux_cfg.refresh_mainmenu()
        with open(pxelinux_cfg_dir + '/default', 'r') as ifile:
            lines = ifile.readlines()
        def_cfg = "\n".join(lines)
        logging.debug(def_cfg)


if __name__ == '__main__':
    unittest.main()
