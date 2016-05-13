import contextlib
import logging
import os
import subprocess


LOG = logging.getLogger(__name__)

GLOBAL_PWD = ['.']


class CommandError(Exception):
    """Shell command exceptions"""


@contextlib.contextmanager
def cd(directory):
    """A context manager for switching the current working directory when

    using the local() function. Not thread safe.
    """

    global GLOBAL_PWD
    GLOBAL_PWD.append(directory)
    yield
    if len(GLOBAL_PWD) > 1:
        GLOBAL_PWD.pop()


def local(cmd, capture=True, pipefail=False, log_method='debug', env=None,
          raise_error=False):
    """Run a command locally. return code, Output as return value."""

    log_method = getattr(LOG, log_method)

    if len(GLOBAL_PWD) > 1:
        cmd = 'cd %s && %s' % (GLOBAL_PWD[-1], cmd)

    if pipefail:
        cmd = 'set -o pipefail && ' + cmd

    env_vars = dict(os.environ.items() + env.items()) if env else os.environ

    log_method('[local] run: %s' % cmd)
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, env=env_vars,
                               executable='/bin/bash')
    buffer_ = []

    while True:
        line = process.stdout.readline()
        if capture:
            buffer_.append(line)
        if isinstance(line, str):
            log_method('[local] out: %s' %
                       unicode(line.rstrip(), errors='ignore'))
        if line == '' and process.poll() is not None:
            break
        if 'KILL STACK.SH' in line:
            process.terminate()
            return 0, ''.join(buffer_)
    if raise_error and process.returncode:
        raise CommandError('Failed to execute: %s' % cmd)
    return process.returncode, ''.join(buffer_)
