import unittest
import os

from node import RemoteNode
from node import LocalNode


class TestStringMethods(unittest.TestCase):

    def test_node(self):
        local = LocalNode()
        remote = RemoteNode('127.0.0.1',
                            username=os.environ.get('USER'),
                            identity=os.environ.get('HOME') + '/.ssh/id_rsa')
        for i in [remote, local]:
            i.pwd()
            i.ls('notexisting', die=False)
            print('Status:', i.status)
            print('Output:', i.stdout.rstrip())
            print('Errors:', i.stderr)
        for i in [local, remote]:
            i.shell('hostname', 'false', 'date', 'true', stop=True,
                    quiet=True, die=False)
            print('Status:', i.status)
            print('Output:', i.stdout.rstrip())
            print('Errors:', i.stderr)

    def test_node_wait_for_substr(self):
        remote = RemoteNode('127.0.0.1',
                            username=os.environ.get('USER'),
                            identity=os.environ.get('HOME') + '/.ssh/id_rsa')
        self.assertTrue(remote.wait_for_substr(cmd="echo _substr_", substr="_substr_"))
        with self.assertRaises(Exception):
            remote.wait_for_substr(cmd="echo _substr_",
                                   substr="__not_exist_string", timeout=10)

    def test_node_not_exists(self):
        # 192.0.2.1 is part of  TEST-NET-1 and should not be used
        # https://tools.ietf.org/html/rfc5737
        remote = RemoteNode('192.0.2.1',
                            username=os.environ.get('USER'),
                            identity=os.environ.get('HOME') + '/.ssh/id_rsa')
        with self.assertRaises(Exception):
            remote.shell('ls -la ', )

    def test_node_wait(self):
        local = LocalNode()
        self.assertTrue(
            local.wait_for_node(host='127.0.0.1', attempts=2, timeout=5))
        self.assertFalse(
            local.wait_for_node(host='192.0.2.1', attempts=2, timeout=5))

    def test_node_wait(self):
        local = LocalNode()
        self.assertTrue(
            local.wait_for_port(host='127.0.0.1', attempts=2, timeout=5))
        #self.assertFalse(
        with self.assertRaises(Exception):
            local.wait_for_port(host='192.0.2.1', attempts=2, timeout=5)

    def test_node_send(self):
        remote = RemoteNode('127.0.0.1',
                            username=os.environ.get('USER'),
                            identity=os.environ.get('HOME') + '/.ssh/id_rsa')
        remote.shell('rm -f  /tmp/passwd')
        self.assertEqual(remote.send('/etc/passwd', ), 0, "Check exit code")
        self.assertEqual(remote.shell('ls -la /tmp/passwd'),
                         0, "Send check exit code")

    def test_node_receive(self):
        remote = RemoteNode('127.0.0.1',
                            username=os.environ.get('USER'),
                            identity=os.environ.get('HOME') + '/.ssh/id_rsa')
        remote.shell('mkdir -p /tmp/test_source /tmp/test_result')
        remote.shell('rm -f  /tmp/test_source/* ; rm -f  /tmp/test_result/* ')
        remote.shell('echo 12345 >  /tmp/test_source/a')
        remote.shell('echo 67890 >  /tmp/test_source/b')
        self.assertEqual(remote.receive('/tmp/test_source/*',
                                        target='/tmp/test_result'), 0,
                         "Check exit code")
        self.assertEqual(remote.shell('ls -la /tmp/test_result/a'),
                         0, "Receive check exit code")
        self.assertEqual(remote.shell('ls -la /tmp/test_result/b'),
                         0, "Receive check exit code")


if __name__ == '__main__':
    unittest.main()
