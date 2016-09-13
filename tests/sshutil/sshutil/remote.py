"""This module contains class that represents a host reachable by SSH."""

import logging
import paramiko
import re
import select


LOG = logging.getLogger(__name__)


class RemoteError(Exception):
    """Remote command exceptions"""


class RemoteClient(object):
    """Representation of a host reachable by SSH"""

    def __init__(self, host_ip, user, password=None):
        """
        :param host_ip: IP address of host
        :param user: Username of user to login with
        :param password: Password of user to login with
        :param alt_logger: Alternative logger to use instead of this module's
                           logger. Used only in run() method.
        :param alt_log_method: Alternative logger method to use when
                               alt_logger is enabled.
        """
        self.host_ip = host_ip
        self.user = user
        self.password = password
        self.client = None
        self.last_exit_status = None

    def run(self, cmd, capture=True, sudo=False, env_vars=None,
            raise_error=False, log_method='debug', feed_input=None):
        """Run a command on the host and return its output
        :param cmd: Command to run on host
        :param capture: Whether to save and return output from command run
        :param sudo: add sudo before command
        :param env_vars: dict that contains environment variable to be set
        :param raise_error: raise exception if exit status is not zero.
        :param log_method: log method of logger.
        """
        log_method = getattr(LOG, log_method)
        if not self.client:
            self._set_client()

        transport = self.client.get_transport()
        channel = transport.open_session()
        channel.set_combine_stderr(True)
        env_cmd = ""
        if env_vars:
            for var, value in env_vars.iteritems():
                env_cmd += 'export %s=%s;' % (var, value)
            cmd = '%s %s' % (env_cmd, cmd)

        feed_password = False
        if sudo and self.user != "root":
            cmd = "sudo -S -p '' %s" % cmd
            feed_password = self.password is not None and (
                len(self.password) > 0)

        log_method('[%s] run: %s' % (self.host_ip, cmd))
        channel.exec_command(cmd)

        buffer_ = []  # This should probably be a limited-length buffer
        line = []
        seen_cr = False

        def flush(text):
            if isinstance(text, str):
                log_method('[%s] out: %s' % (self.host_ip,
                           unicode(text.rstrip(), errors='ignore')))

        def has_newline(bytelist):
            return '\r' in bytelist or '\n' in bytelist

        if feed_password:
            channel.sendall(self.password + '\n')

        if feed_input:
            channel.sendall(feed_input + '\n')

        while not channel.exit_status_ready():
            rlist, wlist, xlist = select.select([channel], [], [], 10.0)
            # wait until ready for reading
            if len(rlist) > 0:
                bytelist = channel.recv(512)
                if capture:
                    buffer_.append(bytelist)

                # empty byte signifies EOS
                if bytelist == '':
                    if line:
                        flush(''.join(line))
                    break

                if bytelist[-1] == '\r':
                    seen_cr = True
                if bytelist[0] == '\n' and seen_cr:
                    bytelist = bytelist[1:]
                    seen_cr = False

                while has_newline(bytelist) and bytelist != '':
                    # at most 1 split !
                    cr = re.search('(\r\n|\r|\n)', bytelist)
                    if cr is None:
                        break
                    end_of_line = bytelist[:cr.start(0)]
                    bytelist = bytelist[cr.end(0):]

                    if has_newline(end_of_line):
                        end_of_line = ''

                    flush(''.join(line) + end_of_line + '\n')
                    line = []

                line += [bytelist]
        self.last_exit_status = channel.recv_exit_status()
        if raise_error and self.last_exit_status:
            raise RemoteError('In host %s failed to execute: %s' %
                              (self.host_ip, cmd))
        return ''.join(buffer_)

    def scp(self, src, dest, log_method='debug'):
        """Transfers a local file to the remote host. src is a relative or
        absolute path to a file. dest is the absolute path on the destination
        host."""
        log_method = getattr(LOG, log_method)
        if not self.client:
            self._set_client()

        sftp = paramiko.SFTPClient.from_transport(self.client.get_transport())
        file_ = src.rpartition('/')[-1]
        sftp.put(src, '/'.join([dest.rstrip('/'), file_]))
        log_method('[%s] scp: %s to %s' % (self.host_ip, src, dest))
        sftp.close()

    def get(self, src, dest, log_method='debug'):
        """Transfers a remote file to the local host. src is a relative or
        absolute path to a file. dest is the absolute path on the destination
        host."""
        log_method = getattr(LOG, log_method)
        if not self.client:
            self._set_client()

        sftp = paramiko.SFTPClient.from_transport(self.client.get_transport())
        file_ = src.rpartition('/')[-1]
        sftp.get(src, '/'.join([dest.rstrip('/'), file_]))
        log_method('[%s] get: %s to %s' % (self.host_ip, src, dest))
        sftp.close()

    def reload_client(self):
        if self.client:
            self.client.close()

        self._set_client()

    def check_connection(self):
        self._set_client()

    def _set_client(self):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(self.host_ip, username=self.user,
                            password=self.password)
