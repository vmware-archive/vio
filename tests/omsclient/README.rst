oms-client
=============

A python library wraps oms rest api client.


Installation
=============

 python setup.py install

 pip install --index-url http://p3-pypi.eng.vmware.com:3141/slave/dev/+simple --trusted-host p3-pypi.eng.vmware.com oms-client


Usage
======
.. code:: python

  oms_ctl = OmsController('192.168.111.151', 'root', 'vmware')
  resp = oms_ctl.create_deployment_plan(spec_str)


