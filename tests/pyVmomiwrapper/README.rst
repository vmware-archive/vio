pyVmomiwrapper
=============

This module wraps pyVmomi.


Installation
=============

 python setup.py install

 pip install --index-url http://p3-pypi.eng.vmware.com:3141/slave/dev/+simple --trusted-host p3-pypi.eng.vmware.com pyVmomiwrapper


Usage
======
.. code:: python

  import ssl
  
  from pyVmomi import vim
  
  from vmwareapi import VirtualCenter
  from vmwareapi import VM
  from vmwareapi import Host
  from vmwareapi import DataStore
  from vmwareapi import Network
  from vmwareapi import Cluster
  from vmwareapi import Vapp
  from vmwareapi import DistributedVirtualSwitch
  from vmwareapi import DistributedVirtualPortgroup
  

  with VirtualCenter('192.168.111.1', 'root', 'vmware') as vc:
    # Create data center
    dc = vc.create_datacenter('dc-01')
    print "dc: %s(%s)" % (dc.name, dc.moid)
    # Get data center
    dc = vc.get_datacenter('openstack-dc-01')
    print "dc: %s(%s)" % (dc.name, dc.moid)
    # Get managed object attributes
    print "dc.datastoreFolder: %s" % dc.datastoreFolder
    # Search entities under vc by name
    vm = vc.get_entities_by_name(VM, 'VIO-DB-1')[0]
    print "vm: %s(%s)" % (vm.name, vm.moid)
    host = vc.get_entities_by_name(Host, 'sin2-openstack-006.eng.vmware.com')[0]
    print "host: %s(%s)" % (host.name, host.moid)
    ds = vc.get_entities_by_name(DataStore, 'vsanDatastore')[0]
    print "ds: %s(%s)" % (ds.name, ds.moid)
    net = vc.get_entities_by_name(Network, 'VM Network')[0]
    print "net: %s(%s)" % (net.name, net.moid)
    cluster = vc.get_entities_by_name(Cluster, 'nova-cluster')[0]
    print "cluster: %s(%s)" % (cluster.name, cluster.moid)
    # Search entities under vc by regex
    vapp = vc.get_entities_by_regex(Vapp, r'^VMware-OpenStack.*\d$')[0]
    print "vapp: %s(%s)" % (vapp.name, vapp.moid)
    # Create dvs
    dc = vc.get_datacenter('openstack-dc-01')
    dvs_spec = vim.DistributedVirtualSwitch.CreateSpec()
    dvs_config = vim.dvs.VmwareDistributedVirtualSwitch.ConfigSpec()
    dvs_config.name = 'test-dvs'
    dvs_config.host = []
    dvs_spec.configSpec = dvs_config
    dvs = dc.create_dvs(dvs_spec)
    print "dvs: %s(%s)" % (dvs.name, dvs.moid)
    # Search entities under data center by name
    vm = dc.get_entities_by_name(VM, 'VIO-DB-1')[0]
    print "vm: %s(%s)" % (vm.name, vm.moid)
    host = dc.get_entities_by_name(Host, 'sin2-openstack-006.eng.vmware.com')[0]
    print "host: %s(%s)" % (host.name, host.moid)
    ds = dc.get_entities_by_name(DataStore, 'vsanDatastore')[0]
    print "ds: %s(%s)" % (ds.name, ds.moid)
    net = dc.get_entities_by_name(Network, 'VM Network')[0]
    print "net: %s(%s)" % (net.name, net.moid)
    cluster = dc.get_entities_by_name(Cluster, 'nova-cluster')[0]
    print "cluster: %s(%s)" % (cluster.name, cluster.moid)
    dvs = dc.get_entities_by_name(DistributedVirtualSwitch, 'VIO-Data')[0]
    print "dvs: %s(%s)" % (dvs.name, dvs.moid)
    # Search entities under data center by regex
    vapp = dc.get_entities_by_regex(Vapp, r'^VMware-OpenStack.*\d$')[0]
    print "vapp: %s(%s)" % (vapp.name, vapp.moid)
    # Add a nic
    dvpg = dc.get_entities_by_name(DistributedVirtualPortgroup, 'dvp-vio-external')[0]
    vm.add_nic(dvpg)
    # Retrieve and update vpx settings
    option_value = vc.query_vpx_settings('vpxd.httpClientIdleTimeout')
    print option_value[0].key, option_value[0].value
    option_value = vc.query_vpx_settings('config.vmacore.http.readTimeoutMs')
    print option_value[0].key, option_value[0].value
  
    option_values = {'config.vmacore.http.readTimeoutMs': '600000',
             'vpxd.httpClientIdleTimeout': 900}
    vc.update_vpx_settings(option_values)
    print '------update settings------'
    option_value = vc.query_vpx_settings('vpxd.httpClientIdleTimeout')
    print option_value[0].key, option_value[0].value
    option_value = vc.query_vpx_settings('config.vmacore.http.readTimeoutMs')
    print option_value[0].key, option_value[0].value



