from copy import deepcopy

from pytest import raises, mark

from teuthology.config import config
from teuthology.provision import pelagos
import teuthology.parallel

import json
import shutil
import os

test_config = dict(pelagos=dict(
    endpoint='http://localhost:5000/',
    machine_types='type1,type2',
))

test_pxelinux_cfg_root_dir = '/tmp/tftp'
test_pxelinux_cfg_dir = test_pxelinux_cfg_root_dir + '/pxelinux.cfg'


class TestPelagos(object):
    klass = pelagos.Pelagos

    def setup(self):
        config.load(deepcopy(test_config))

    def test_get_types(self):

        types = pelagos.get_types()
        assert types == test_config['pelagos']['machine_types'].split(',')

    def test_do_request(self):
        obj = self.klass('name.fqdn', 'type', '1.0')
        nodelist_answer = obj.do_request('nodes', data='', method='GET')
        # print("----" + nodelist_answer.text)
        nodelist = json.loads(nodelist_answer.text)
        assert len(nodelist['nodes']) == 9

    def test_create_negative(self):
        shutil.rmtree(test_pxelinux_cfg_root_dir, ignore_errors=True)
        node = 'test_node_not_exists_xxxxxxxx'
        obj = self.klass(node, 'sle_15sp1', '0.1.1')
        with raises(Exception):
            assert obj.create()
        # assert no_os_answer_res.status_code == 404
        # print("\nNo node http response:\n" + no_os_answer_res.text)

        # prepare directory structure on localhost
        node = 'test_node'
        obj = self.klass(node, 'sle_15sp1_xxx', '0.1.1')
        with raises(Exception):
            assert obj.create()
        # assert no_os_answer_res.status_code == 404
        # print("\nNo os http response:\n" + no_os_answer_res.text)

    def test_create(self):
        # prepare directory structure on localhost
        shutil.rmtree(test_pxelinux_cfg_root_dir, ignore_errors=True)
        os.makedirs(test_pxelinux_cfg_dir)
        os_id = 'sle-15.1'
        test_dir = '%s/%s' % (test_pxelinux_cfg_root_dir, os_id)
        # print("Create test dir: " + test_dir)
        os.makedirs(test_dir)

        # run action
        node = 'test_node'
        obj = self.klass(node, 'sle', '15.1')
        deploy_answer = obj.create()
        deploy_res = json.loads(deploy_answer.text)
        assert deploy_res['status'] == 'done'
        assert deploy_res['node']['node'] == node

    def test_create_5(self):
        # prepare directory structure on localhost
        shutil.rmtree(test_pxelinux_cfg_root_dir, ignore_errors=True)
        os.makedirs(test_pxelinux_cfg_dir)
        test_dir = test_pxelinux_cfg_root_dir + '/sle-15.1'
        print("Create test dir: " + test_dir)
        os.makedirs(test_dir)

        # run action
        nodes = ['tnode1', 'tnode2', 'tnode3', 'tnode4']
        objs = dict()
        for node in nodes:
            objs[node] = self.klass(node, 'sle', '15.1')

        with teuthology.parallel.parallel() as p:
            for node in nodes:
                p.spawn(provision_sim, objs[node])


def provision_sim(obj):
    deploy_answer = obj.create()
    deploy_res = json.loads(deploy_answer.text)
    # assert deploy_res['status'] == 'done'
    # assert deploy_res['node']['node'] == node
