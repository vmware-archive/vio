Tests that help you ensure your Openstack Env is healthy
=========================================================
Tempest is a common tool to verify your Openstack. Follow this Guide you can
run tempest tests to check your existed VIO setup.


System dependencies installation
=================================
Set up an Ubuntu 14.04(or above) VM, make sure it has internet connectivity.

* Install required libs: python-dev libffi-dev libssl-dev git swig libxml2-dev libxslt-dev.
* Install pip: See https://pip.pypa.io/en/stable/installing/
* Install virtualenv with pip.

.. code:: shell

  apt-get -y install python-dev libffi-dev libssl-dev git swig libxml2-dev libxslt-dev
  wget https://bootstrap.pypa.io/get-pip.py
  python get-pip.py
  pip install virtualenv


Installation
=============
Clone this repository from github, then go to ``vio/tests`` folder.
Run ``./install.sh`` to install these test projects. Run 
``source .venv/bin/activate`` to activate them. 

Type command ``panda tempest install -h`` to check if ``panda`` is installed.


Configuration
==============
Move this Ubuntu VM to your VIO network, make sure it has a IP address in the
same L2 subnet with VIO private VIP. The VM should be able to reach private VIP
without routing. Add another NIC to the VM and make sure it has connectivity to
NSX Edge external network.

If the MTU of the networks are larger than 1500, set them to a small value with
below commands:

.. code:: shell

  ip li set mtu 1200 dev eth0
  ip li set mtu 1200 dev eth1


Run command ``panda tempest config -h`` to get the help information about all
parameters to configure tempest in your setup.

Below are sample commands to configure tempest according to VIO neutron and
keystone backend.

.. code:: shell

  # Configure tempest against a NSXv neutron/SQL keystone backend VIO
  panda tempest config '192.168.111.160' 'admin' 'vmware' 'nsxv' --ext-cidr '192.168.112.0/24' --ext-start-ip '192.168.112.170' --ext-end-ip '192.168.112.200' --ext-gateway '192.168.112.1' --nsx-manager '192.168.111.15' --nsx-user 'admin' --nsx-password 'default'
  # Configure tempest against a NSXv neutron/LDAP keystone backend VIO.
  panda tempest config '192.168.111.160' 'vioadmin@vio.com' 'VMware1!' 'nsxv' --credentials-provider 'pre-provisioned' --user1 'xiaoy@vio.com' --user1-password 'VMware1!' --user2 'sren@vio.com' --user2-password 'VMware1!' --ext-cidr '192.168.112.0/24' --ext-start-ip '192.168.112.170' --ext-end-ip '192.168.112.200' --ext-gateway '192.168.112.1' --nsx-manager '192.168.111.15' --nsx-user 'admin' --nsx-password 'default'
  # Configure tempest against a DVS neutron/SQL keystone backend VIO.
  panda tempest config '192.168.111.153' 'admin' 'vmware' 'dvs'


Note:

* Make sure you run them in the directory ``tests/``
* For LDAP backend, you should find available LDAP users like ``xiaoy@vio.com`` and ``sren@vio.com`` as the parameters. Replace ``vioadmin@vio.com`` to the admin user of your VIO setup.
* '192.168.112.0/24', '192.168.112.170' etc. are the Edge external network configurations in your VIO setup. Tempest tests will ssh through floating IP and verify instances.
* '192.168.111.160' 'admin' 'vmware' are the Private VIP and authentication of your VIO setup, change them to yours.

Check generated configurations in ``tempest/etc/tempest.conf`` afterward.


Run test suites
================
Make a report directory and kick off tests with below commands:

.. code:: shell

  mkdir reports
  panda tempest run 'keystone,glance,nova,cinder,neutron,heat,scenario' --report-dir reports/

Note: HTML reports will be generated to specified report dir and logs of tempest
are written to tempest/tempest.log. Any error during 'panda' command please refer
to panda.log. Only scenario is recommended for health verification.


