sshutil
=============

A utility module to connect to and execute commands on remote linux machine. Also supports SCP to/from remote machine.


Installation
=============

 python setup.py install

 pip install --index-url http://p3-pypi.eng.vmware.com:3141/slave/dev/+simple --trusted-host p3-pypi.eng.vmware.com ssh-util


Usage
======

See tests/test_remote.py

Example to use the cli:
``ssh_exec '10.111.160.16' 'viouser' 'vmware' 'restart oms' --sudo``
