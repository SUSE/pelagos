import flask_tasks
import json
import logging
import shutil
import sys
import os
import time
import unittest

from os import path

import network_manager
import pelagos
import hw_node
import pxelinux_cfg
import threaded_logging

test_pxelinux_cfg_root_dir = '/tmp/tftp'
test_conman_dir = '/tmp/conman'
test_log_dir = '/tmp/pelagos_logs/'
test_pxelinux_cfg_dir = test_pxelinux_cfg_root_dir + '/pxelinux.cfg'


class pelagosTest(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        shutil.rmtree(test_log_dir, ignore_errors=True)
        os.makedirs(test_log_dir, exist_ok=True)
        threaded_logging.log_prefix = test_log_dir
        threaded_logging.config_root_logger()

    def setUp(self):
        network_manager.data_file = 'test/test_network_cfg.json'
        flask_tasks.clean_call_timeout_sec = 1
        flask_tasks.data_life_time_sec = 300

        shutil.rmtree(test_pxelinux_cfg_root_dir, ignore_errors=True)
        os.makedirs(test_pxelinux_cfg_dir, exist_ok=True)

        shutil.rmtree(test_conman_dir, ignore_errors=True)
        os.makedirs(test_conman_dir, exist_ok=True)

        pxelinux_cfg.pxelinux_cfg_dir = test_pxelinux_cfg_dir
        pxelinux_cfg.tftp_cfg_dir = test_pxelinux_cfg_root_dir

        shutil.rmtree(test_log_dir+'/*', ignore_errors=True)

        pelagos.app.testing = True
        pelagos.app.simulate_mode = 'fast'
        self.app = pelagos.app.test_client()

    @classmethod
    def tearDownClass(self):
        flask_tasks.stop_cleanup = True
        logging.debug('5s timeout for cleanup thread stop')
        time.sleep(5)

    def tearDown(self):
        shutil.rmtree(test_pxelinux_cfg_root_dir, ignore_errors=True)
        shutil.rmtree(test_conman_dir, ignore_errors=True)
        logging.debug("tearDown completed")

    def test_pxe_root(self):
        response = self.app.get('/')
        self.assertGreater(
            str(response.get_data().decode(sys.getdefaultencoding())).
            find("for access to REST functionality"),
            -1,
            "check /"
        )

    def test_pxe_nodes(self):
        response = self.app.get('/nodes')
        print(response)
        status = json.loads(response.get_data().decode(
            sys.getdefaultencoding()))
        logging.debug(status)
        self.assertEqual(
            status['nodes'][0]['mac'],
            'aa:bb:cc:dd:00:aa',
            "check /nodes 1"
        )
        self.assertEqual(
            status['nodes'][1]['node'],
            'test_node',
            "check /nodes 2"
        )

    def test_pxe_node(self):
        response = self.app.get('/node/test_node')
        node = json.loads(response.get_data().decode(
            sys.getdefaultencoding()))
        logging.debug(node['pxe'])
        self.assertEqual(
            node['node']['mac'],
            'AA:bb:cc:dd:00:73',
            "check /nodes"
        )
        self.assertEqual(
            node['pxe']['os'],
            pxelinux_cfg.const_default_pxe,
            "check /pxe/api/nodes"
        )

    def test_check_os(self):
        response = self.app.get('/check_image/not_set_os_image')

        logging.debug(response.get_data(as_text=True))
        self.assertRegex(response.get_data(as_text=True),
                         r'No\s+os\s+image\s+\[not_set_os_image\]\s+found')
        os_id = 'sle-15.1-0.1.1-29.1'
        os.makedirs('%s/%s' % (test_pxelinux_cfg_root_dir, os_id))
        response = self.app.get('/check_image/%s' % os_id)
        logging.debug(response.get_data(as_text=True))
        status = json.loads(response.get_data().decode(
            sys.getdefaultencoding()))
        self.assertEqual(
            status['os'],
            os_id,
            "check #1 check_image/" + os_id
        )
        os_id1 = 'sle-15.1-0.0.1-29.1'
        os.makedirs("%s/%s" % (test_pxelinux_cfg_root_dir, os_id1))
        response = self.app.get('/check_image/' + os_id1)
        status = json.loads(response.get_data().decode(
            sys.getdefaultencoding()))
        self.assertEqual(
            status['os'],
            os_id1,
            "check #2 check_image/" + os_id1
        )

    def test_pxe_bootrecord_node(self):
        # create boot file and check it
        response = self.app.get('/node/bootrecord/test_node/local')
        logging.debug(response.get_data().decode(sys.getdefaultencoding()))
        node = json.loads(response.get_data().decode(
            sys.getdefaultencoding()))
        self.assertEqual(
            node['node']['mac'],
            'AA:bb:cc:dd:00:73',
            "check /node/bootrecord 1"
        )

        # calculate predefined name
        pxe_file = test_pxelinux_cfg_dir + '/01-aa-bb-cc-dd-00-73'
        self.assertTrue(os.path.isfile(pxe_file),
                        'Check pxe file existence')
        logging.debug("open created file for testing: " + pxe_file)
        pxe_file_data = ''
        with open(pxe_file, 'r') as ifile:
            pxe_file_data = ifile.readlines()
        logging.debug("".join(pxe_file_data))
        self.assertRegex("".join(pxe_file_data), 'LOCALBOOT -1',
                         'Check local boot content')

        logging.info("remove boot file and check it")
        response = self.app.get('/node/rmbootrecord/test_node')
        logging.warning(response.get_data().decode(sys.getdefaultencoding()))
        pxe_file = test_pxelinux_cfg_dir + '/01-aa-bb-cc-dd-00-7c'
        self.assertFalse(os.path.isfile(pxe_file), 'Check pxe file absence')

    def test_pxe_provision_node_negative(self):
        pelagos.app.simulate_mode = ''
        # unknown os
        location, id = self.do_flask_task_request(
            '/node/provision',
            dict(os='test_os', node='test_node'),
            'no image test "test_os" ',
            '404 NOT FOUND')
        time.sleep(3)
        response_2 = self.app.get(location)
        logging.debug("next level response headers #1")
        logging.debug(response_2.get_data())
        self.assertRegex(response_2.get_data(as_text=True),
                         r'No\s+os\s+image\s+\[test_os\]\s+found')
        # timeout for clear output
        time.sleep(1)
        # unknown node
        os_id = 'sle-15.1-0.1.1-29.1'
        test_dir = '%s/%s' % (test_pxelinux_cfg_root_dir, os_id)
        logging.debug("Create test dir: " + test_dir)
        os.makedirs(test_dir)
        location, id = self.do_flask_task_request(
            '/node/provision',
            {'os': os_id,
             'node': 'not_exists_test_node'},
            'unknown node test',
            '404 NOT FOUND')
        time.sleep(3)
        response_2 = self.app.get(location)
        logging.debug("next level response headers #2")
        logging.debug(response_2.get_data())
        self.assertRegex(response_2.get_data(as_text=True),
                         r'No\s+node\s+\[not_exists_test_node\]\s+found')

        # timeout for clear output
        time.sleep(1)
        # ipmi failure
        hw_node.ipmi_pass = 'nopass'
        hw_node.ipmi_user = 'nouser'
        pxelinux_cfg.wait_node_is_ready_timeout = 5
        pxelinux_cfg.default_undoubted_hw_start_timeout = 1
        location, id = self.do_flask_task_request(
            '/node/provision',
            {'os': os_id,
             'node': 'test_node'},
            'provision timeout test')
        logging.debug('Wait for bmc failure')
        time.sleep(30)
        response_3 = self.app.get(location)
        logging.debug('next level response headers #3')
        logging.debug(response_3.get_data())
        self.assertRegex(response_3.get_data(as_text=True),
                         '502 Bad Gateway')
        self.assertRegex(response_3.get_data(as_text=True),
                         'BMCException ipmitool call failed')

        # connect to node timeout
        # while no frozen output
        hw_node.ipmitool_bin = 'echo'
        hw_node.default_port_lookup_attempts = 2
        hw_node.default_port_lookup_timeout = 1
        hw_node.conman_log_prefix = '/tmp/conman.console.'
        shutil.copyfile('test/conman.console.test_node1',
                        '/tmp/conman.console.test_node')

        location, tid = self.do_flask_task_request(
            '/node/provision',
            {'os': os_id,
                'node': 'test_node'},
            'provision timeout test')
        logging.debug('Wait for server reaction 120s')
        time.sleep(20)
        response_4 = self.app.get(location)
        logging.debug('next level response headers #4')
        logging.debug(response_4.get_data())
        self.assertRegex(response_4.get_data(as_text=True),
                         '504 Gateway Timeout')
        self.assertRegex(response_4.get_data(as_text=True),
                         'Caught TimeoutException')

        # frozen conman output/max restarts
        pxelinux_cfg.wait_node_is_ready_timeout = 30
        hw_node.default_conman_line_max_age = 3
        hw_node.default_cold_restart_timeout = 1
        location, tid = self.do_flask_task_request(
            '/node/provision',
            {'os': os_id,
                'node': 'test_node'},
            'provision timeout test')
        logging.debug('Wait for server reaction')
        time.sleep(20)
        response_5 = self.app.get(location)
        logging.debug('next level response headers #5')
        logging.debug(response_5.get_data())
        self.assertRegex(response_5.get_data(as_text=True),
                         '502 Bad Gateway')

    def test_provision_log_cleanup(self):
        (os_id, test_dir) = self.prepare_correct_boot_env()
        # scenario:
        # - start a provision
        # - check existence  log on fs
        # - wait for end of cleanup time
        # - check log cleanup

        flask_tasks.data_life_time_sec = 5
        time.sleep(10)
        location, tid = self.do_flask_task_request(
            '/node/provision',
            {'os': os_id,
             'node': 'test_node'},
            "test thread")
        self.assertIsNotNone(flask_tasks.tasks[tid],
                             'Provision thread exists')
        log_file_name = flask_tasks.tasks[tid]['log_file']
        self.assertTrue(path.exists(log_file_name))
        log_data = self.app.get('/tasks/log/'+tid)
        self.assertRegex(log_data.get_data(as_text=True),
                         r'Found\s+os\s+\[sle-15.1-0.1.1-29.1\]',
                         'Chek log content')
        self.assertEqual(flask_tasks.tasks[tid]['log_handler'],
                        logging.getLogger().handlers[2]
                        )

        time.sleep(15)
        logging.debug("Cleanup should happens, check it")
        self.assertFalse(tid in flask_tasks.tasks)
        self.assertFalse(path.exists(log_file_name))
        removed_log_result = self.app.get('/tasks/log/'+tid)
        self.assertEqual(removed_log_result.status,
                         '404 NOT FOUND', 'Log removed')
        self.assertEqual(len(logging.getLogger().handlers),2)


    def test_pxe_provision_node_threaded(self):
        (os_id, test_dir) = self.prepare_correct_boot_env()

        # start 3 items in queue
        # check that executed tasks are passed
        location1, id1 = self.do_flask_task_request(
            '/node/provision',
            {'os': os_id,
             'node': 'test_node'},
            "all proper 3 thread test #1")

        location2, id2 = self.do_flask_task_request(
            '/node/provision',
            {'os': os_id,
             'node': 'test_node2'},
            "all proper 3 thread test #2")

        location3, id3 = self.do_flask_task_request(
            '/node/provision',
            {'os': os_id,
             'node': 'test_node3'},
            "all proper 3 thread test #3")

        response_list = self.app.get('tasks/statuses')
        logging.debug(response_list.get_data().
                      decode(sys.getdefaultencoding()))

        # waid end of all
        time.sleep(9)
        response_21 = self.app.get(location1)
        status21 = json.loads(response_21.get_data().
                              decode(sys.getdefaultencoding()))

        response_22 = self.app.get(location2)
        status22 = json.loads(response_22.get_data().
                              decode(sys.getdefaultencoding()))

        response_23 = self.app.get(location3)
        status23 = json.loads(response_23.get_data().
                              decode(sys.getdefaultencoding()))

        statuses_r = self.app.get('/tasks/statuses')
        statuses = json.loads(statuses_r.get_data())
        # logging.debug("++++++++++++++++++++++++++++++++++++++" +
        #              str(statuses))
        self.assertRegex(status21['node']['ip'], "1.2.3.13")
        self.assertRegex(status21['status'], 'done')
        self.assertRegex(statuses[id1]['status'], 'done')
        self.assertRegex(status22['node']['ip'], "1.2.3.14")
        self.assertRegex(status23['node']['ip'], "1.2.3.15")

    def test_provision_thread_stop(self):
        (os_id, test_dir) = self.prepare_correct_boot_env()
        pelagos.app.simulate_mode = 'medium'
        # scenario:
        #  - start thread
        #  - stop theread
        #  - check that it stopped via listing
        #

        location, id1 = self.do_flask_task_request(
            '/node/provision',
            {'os': os_id,
             'node': 'test_node'},
            'provision for dismissing ')
        # do some untis testing of flask_tasks here because
        # we cannot test without structure preprared by flask
        import flask_tasks
        from flask_tasks import NoTaskException, NoThreadException

        with self.assertRaises(NoTaskException) as task_exp:
            flask_tasks.find_taks_by_node('not_existed_node')

        with self.assertRaises(NoTaskException) as thr_exp:
            flask_tasks.find_thread_by_task('123321')
        test_task = flask_tasks.find_taks_by_node('test_node')
        self.assertEqual(id1, test_task, 'Correct task found')

        tid, tobj = flask_tasks.find_thread_by_task(test_task)

        self.assertTrue(tobj.is_alive())

        self.assertEqual(flask_tasks.tasks[test_task]['node'],
                         'test_node', 'check found node')
        self.assertEqual(flask_tasks.tasks[test_task]['stopped'],
                         False, 'check stopped status')
        response = self.app.post('tasks/node/dismiss',
                                 data={'node': 'test_node'})
        logging.debug(response.get_data().decode(sys.getdefaultencoding()))

        self.assertFalse(tobj.is_alive())
        self.assertEqual(flask_tasks.tasks[test_task]['stopped'],
                         True, 'check stopped status')
        response_after_stop = self.app.get(location)
        self.assertRegex(response_after_stop.get_data(as_text=True),
                         r'Stop\ provisioning\ thread\ by\ request')

    def test_reprovision_node(self):
        (os_id, test_dir) = self.prepare_correct_boot_env()
        pelagos.app.simulate_mode = 'medium'
        # scenario:
        # - start node provision #1
        # - start node provision #2
        # - start node provision #3 for other node
        # - check provision #1 was dismissed, #2 and #3 alive

        location1, task_id1 = self.do_flask_task_request(
            '/node/provision',
            {'os': os_id,
             'node': 'test_node'},
            'provision #1 ')
        location2, task_id2 = self.do_flask_task_request(
            '/node/provision',
            {'os': os_id,
             'node': 'test_node'},
            'provision #2 ')
        location3, task_id3 = self.do_flask_task_request(
            '/node/provision',
            {'os': os_id,
             'node': 'test_node2'},
            'provision #3 ')
        response_stopped = self.app.get(location1)
        self.assertRegex(response_stopped.get_data(as_text=True),
                         r'Stop\ provisioning\ thread\ by\ request',
                         'task #1 should be ended')
        response_active = self.app.get(location2)
        self.assertEqual(response_active.status, '202 ACCEPTED',
                         'task #2 should be alive')
        response3 = self.app.get(location2)
        self.assertEqual(response3.status, '202 ACCEPTED',
                         'task #3 should be alive')

    # utility functions for tests
    def do_flask_task_request(self,
                              request,
                              post_dict,
                              prefix,
                              next_level_status='202 ACCEPTED'):
        response = self.app.post(request,
                                 data=post_dict)
        self.assertEqual(response.status, '202 ACCEPTED', prefix)
        logging.debug(prefix + " response headers to request")
        logging.debug(response.headers)
        location = response.headers.get('Location')
        logging.debug(prefix + " Location: " + location)
        taskid = response.headers.get('TaskID')
        logging.debug(prefix + " TaskID: " + taskid)
        # timeout for provision negative tests
        time.sleep(1)
        response_1 = self.app.get(location)
        logging.debug(prefix + " next level response headers")
        logging.debug(response_1.headers)
        self.assertEqual(response_1.status, next_level_status, prefix)
        return location, taskid

    def prepare_correct_boot_env(self):
        os_id = 'sle-15.1-0.1.1-29.1'
        flask_tasks.tasks = {}
        pelagos.app.simulate_mode = 'fast'
        test_dir = '%s/%s' % (test_pxelinux_cfg_root_dir, os_id)
        logging.debug("Create test dir: " + test_dir)
        os.makedirs(test_dir)
        return os_id, test_dir


if __name__ == '__main__':
    unittest.main()
