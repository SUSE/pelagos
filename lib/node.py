import os
import time
import re
import sys
import signal
import subprocess
import logging
import time
import socket

import yaml

log = logging.getLogger(__name__)


def shellcmd(**kwargs):
    username = kwargs.get('user', 'jenkins')
    command = kwargs.get('cmd', None)
    ipaddr = kwargs.get('host', None)
    res, out, err = ssh(cmd=command, host=ipaddr, user=username)
    if res != 0:
        msg = "Error while executing the command '%s'. Error message: '%s'" % (command, err)
        raise(Exception, msg)
    return None


def ssh(**kwargs):
    username = kwargs.get('user', None)
    hostname = kwargs.get('host', None)
    command  = kwargs.get('cmd', None)
    timeout  = kwargs.get('timeout', None)
    workdir  = kwargs.get('cwd', None)
    environ  = kwargs.get('env', None)
    cmd = "ssh -q %s@%s %s" % (username, hostname, command)
    return launch(cmd=cmd, timeout=timeout, env=environ, cwd=workdir)


def launch(**kwargs):
    orig_wd = None
    execution_string = kwargs.get('cmd', None)
    env = kwargs.get('env', None)
    timeout = kwargs.get('timeout', None)
    workdir = kwargs.get('cwd', None)
    quiet   = kwargs.get('quiet', False)
    stdin   = kwargs.get('stdin', None)
    if env is None:
        env = os.environ
    if timeout is None:
        timeout = 60

    if execution_string is None:
        return 256, "", ""
    # Now handle directory changes
    if workdir is not None:
        orig_wd = os.getcwd()
        os.chdir(workdir)
    log.debug("executing the command "+ execution_string)
    process = subprocess.Popen([execution_string],
                                shell=True,
                                stdin=subprocess.PIPE if stdin else None,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                env=env, bufsize=0)
    if orig_wd is not None:
        os.chdir(orig_wd)
    process_rc = None
    handle_process = True
    counter = 0
    stdout = ''
    stderr = ''
    if stdin:
        process.stdin.write(stdin)
    while handle_process:
        counter += 1
        cout, cerr = process.communicate()
        stdout += cout.decode('utf-8')
        stderr += cerr.decode('utf-8')
        if not quiet:
            sys.stdout.write(cout.decode('utf-8'))
            sys.stderr.write(cerr.decode('utf-8'))
        process.poll()
        process_rc = process.returncode
        if process_rc is not None:
            break
        if counter == timeout:
            os.kill(process.pid, signal.SIGQUIT)
        if counter > timeout:
            os.kill(process.pid, signal.SIGKILL)
            process_rc = -9
            break
        time.sleep(1)
    return process_rc, stdout, stderr


class BasicShell:
    stderr = None
    stdout = None
    status = None
    script = None
    show_output = False
    fail_on_error = False

    def shell(self, *cmd, **kwargs):
        pass

    def store_our_err(self, tmpl_file_path):
        with open('{}.stdout'.format(tmpl_file_path), 'w') as f:
            f.write(self.stdout)
        with open('{}.stderr'.format(tmpl_file_path), 'w') as f:
            f.write(self.stderr)


class ToolBox():
    pass

class YamlTools(BasicShell, ToolBox):
    def load_yaml(self, remote_path, **kwargs):
        self.shell('cat %s' % remote_path, **kwargs)
        obj = yaml.safe_load_all(self.stdout)
        return obj
    def dump_yaml(self, remote_path, data, **kwargs):
        text = yaml.dump_all(data, default_flow_style=False)
        self.shell('tee %s' % remote_path, stdin=text.encode(), **kwargs)
        return text

class CommonTools(BasicShell, ToolBox):
    def _shell(self, *args, **kwargs):
        self.shell(" ".join(args), **kwargs)
        return self.stdout

    def ls(self, *args, **kwargs):
        self._shell('ls', *args, **kwargs)
        return self.stdout

    def reboot(self, *args, **kwargs):
        timeout = kwargs.get('timeout', 120)
        self._shell('sudo reboot', *args, **kwargs)
        assert(self.status == 255), self.stderr
        counter = timeout
        while os.system("ping -c1 -W 1 {}".format(self.hostname)) == 0 and counter > 0:
            time.sleep(1)
            counter -= 1
        if counter == 0:
            return False
        #TODO use here wait_for_node
        log.info("{} is down. Waiting for the node ...".format(self.hostname))
        for count in range(1,5):
            response = os.system("ping -c {} -W {} {}".format(count, timeout, self.hostname))
            if response == 0:
                log.info("The ping was successful.")
                return True
        return False

    def wait_for_node(self, *args, **kwargs):
        timeout = kwargs.get('timeout', 120)
        attempts = kwargs.get('attempts', 5)
        # TODO common rules for the class is broken
        # rewrite with self.hostname usage
        hostname = kwargs.get('host', '')
        log.info("Waiting for the node ...".format(hostname))
        for count in range(1, attempts):
            log.debug("\nping -c 2  -W {} {}".format(timeout, hostname))
            response = os.system("ping -c 2  -W {} {}".
                                 format(timeout, hostname))
            if response == 0:
                log.info("The ping was successful.")
                return True
        return False

    def wait_for_port(self, *args, **kwargs):
        #default 5 min
        timeout = kwargs.get('timeout', 5)
        attempts = kwargs.get('attempts', 60)
        # TODO common rules for the class is broken
        # rewrite with self.hostname usage
        hostname = kwargs.get('host', '')
        port = int(kwargs.get('port', '22'))
        # Create a TCP socket
        ex=''
        for count in range (1,attempts):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            print("Attempting [{}] to connect to {} on port {}".format(count,hostname, port))
            result = sock.connect_ex((hostname,port))
            sock.close()
            if result == 0:
                print("Connected to {} on port {}".format(hostname, port))
                return True
            else:
                print("Connection to {} on port {} failed".format(hostname, port))
                print("Reconnect after {}".format(timeout))
            time.sleep(timeout)

        raise Exception("Cannot connect to [{}]".format(hostname))


    def wait_for_substr(self, *args, **kwargs):
        # 5 min by def
        timeout = kwargs.get('timeout', 300)
        # sleep between runs
        sleep  = kwargs.get('sleep', 5)
        substr = kwargs.get('substr', '')
        # use regex matching instead of substring matching
        regex = kwargs.get('regex', '')
        # number of matches to wait for
        count = kwargs.get('count', 1)
        # print output of command on each attempt
        verbose = kwargs.get('verbose', False)
        cmd = kwargs.get('cmd', '')
        log.debug("Arguments:", kwargs)
        print("Waiting for [{}] in output of [{}] the node {}".
                 format(substr or regex, cmd, self.hostname))
        found = 0
        starttime = int(time.time())
        print()
        while (found < count) and (starttime + int(timeout)) > int(time.time()):
            self.shell(cmd, die=False, quiet=True)
            if verbose:
                print("stdout", self.stdout)
                print("stderr:", self.stderr)
            if regex:
                nfound = len(re.findall(regex, self.stdout + self.stderr))
            else:
                nfound = (self.stdout + self.stderr).count(substr)
            if nfound > 0:
                log.info('[{}] found ({}/{})!'.format(substr or regex, nfound, count))
                found = nfound
            else:
                time.sleep(sleep)
        if found < count:
            print("Raising exception on no substr in timeout")
            print("Last stdout:", self.stdout)
            print("Last stderr:", self.stderr)
            raise Exception("Substring [{}] not found for [{}] in [{}] sec.".
                            format(substr or regex, cmd, timeout))
        return True

    def pwd(self):
        self.shell('pwd')
        return self.stdout


class LocalShell(BasicShell):
    def __init__(self):
        self.command = ''


    def shell(self, *cmds, **kwargs):
        raise_exception = kwargs.get('die', True)
        break_execution = kwargs.get('stop', True)
        expected_status = kwargs.get('expect', [0])
        trace           = kwargs.get('trace', True)
        quiet           = kwargs.get('quiet', False)
        print("Command:", "; ".join(cmds))
        print("Arguments:", kwargs)
        if 'quiet' in kwargs :
            kwargs.pop('quiet')
        for i in cmds:
            self.command = i
            if trace:
                print("> {}".format(self.command))
                print("exit code", self.status)
            self.status, self.stdout, self.stderr = \
                launch(cmd=self.command, quiet=quiet, **kwargs)
            if trace:
                print("exit code", self.status)
            if not self.status in expected_status:
                if raise_exception:
                    raise Exception("Command [{}] failed with status {}.".format(self.command, self.status))
                if break_execution:
                    break


class SecureShell(BasicShell):
    def __init__(self, hostname='localhost', username=None, password=None, identity=None, port=22):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.identity = identity
        self.port = port
        self.default_opts = '-q -o StrictHostKeyChecking=no -o ' + \
                            ' UserKnownHostsFile=/dev/null -o ConnectTimeout=10 ' + \
                            '-o ConnectionAttempts=5 '
        self.scp_opts = ' -p -r '
        self.command = ''

    def _cmd(self, cmd, **kwargs):
        trace = kwargs.get('trace', True)
        ssh_cmd = ''
        default_opts = self.default_opts
        if self.identity:
            default_opts += ' -i {}'.format(self.identity)
        if self.port != 22:
            default_opts += ' -p {}'.format(self.port)
        if self.username:
            ssh_cmd = "ssh {} {}@{}".format(default_opts,
                                            self.username, self.hostname)
        else:
            ssh_cmd = "ssh {} {}".format(default_opts, self.hostname)
        self.command = "{} {}".format(ssh_cmd, cmd)
        if trace:
            print("{}> {}".format(self.hostname, self.command))
        self.status, self.stdout, self.stderr = \
            launch(cmd=self.command, **kwargs)

    def _scp_cmd(self, local_file, remote_file, **kwargs):
        trace = kwargs.get('trace', True)
        send =  kwargs.get('send', True)
        print("Remote file or dir:", remote_file)
        print("Local  file or dir:", local_file)

        default_opts = self.default_opts + self.scp_opts
        if self.identity:
            default_opts += ' -i {}'.format(self.identity)
        if self.port != 22:
            default_opts += ' -P {}'.format(self.port)
        if self.username:
            if send:
                self.command = "scp {} {} {}@{}:{}".format(
                    default_opts, local_file, self.username, self.hostname, remote_file)
            else:
                self.command = "scp {} {}@{}:{} {}".format(
                    default_opts, self.username, self.hostname, remote_file, local_file)
        else:
            if send:
                self.command = "scp {} {} {}:{}".format(
                    default_opts, local_file,  self.hostname, remote_file)
            else:
                self.command = "scp {} {}:{} {}".format(
                    default_opts,  self.hostname, remote_file, local_file)
        if trace:
            print("{}> {}".format(self.hostname, self.command))
        self.status, self.stdout, self.stderr = \
            launch(cmd=self.command, **kwargs)

    def shell(self, *cmds, **kwargs):
        print("Hostname:", self.hostname)
        print("Command:", "; ".join(cmds))
        print("Arguments:", kwargs)
        raise_exception = kwargs.get('die', True)
        break_execution = kwargs.get('stop', True)
        expected_status = kwargs.get('expect', [0])
        trace           = kwargs.get('trace', True)
        quiet           = kwargs.get('quiet', False)
        if 'quiet' in kwargs:
            kwargs.pop('quiet')
        for i in cmds:
            self._cmd(i, quiet=quiet, trace=trace, **kwargs)
            if not(self.status in expected_status):
                if raise_exception:
                    raise Exception("Command [{}] failed with status {}.".format(self.command, self.status))
                if break_execution:
                    break
        return self.status

    def _transfer(self, send,  *files, **kwargs):
        print("Arguments:", kwargs)
        print("Work dir:", os.getcwd())
        print("Files to send:", "; ".join(files))
        raise_exception = kwargs.get('die', True)
        break_execution = kwargs.get('stop', True)
        expected_status = kwargs.get('expect', [0])
        trace           = kwargs.get('trace', True)
        quiet           = kwargs.get('quiet', False)
        if 'quiet' in kwargs:
            kwargs.pop('quiet')
        #local_file = ''
        #remote_file = ''
        for f in files:
            if send:
                local_file = f
                remote_file = kwargs.get('remote_target')
            else:
                remote_file = f
                local_file = kwargs.get('local_target')
            self._scp_cmd(local_file, remote_file, send=send, quiet=quiet, trace=trace, **kwargs)
            if not(self.status in expected_status):
                if raise_exception:
                    raise Exception("Command [{}] failed with status {}.".format(self.command, self.status))
                if break_execution:
                    break
        return self.status

    def send(self, *files, **kwargs):
        print("Hostname for sending :", self.hostname)
        remote_target = kwargs.get('target', '/tmp/')
        return self._transfer(True, *files, remote_target=remote_target,
                              **kwargs)

    def receive(self, *files, **kwargs):
        print("Receiving from hostname:", self.hostname)
        local_target = kwargs.get('target', '.')
        return self._transfer(False, *files, local_target=local_target,
                              **kwargs)



class LocalNode(LocalShell, CommonTools):
    pass


class RemoteNode(SecureShell, CommonTools):
    pass

