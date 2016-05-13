"""Wrapper library for pyVmomi"""

import logging
import re

import pyVmomi
from pyVmomi import vim
import ssl

import task


LOG = logging.getLogger(__name__)


def connect(host, user, password, verify=True):
    if verify:
        context = None
    else:
        context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        context.verify_mode = ssl.CERT_NONE

    stub = pyVmomi.SoapStubAdapter(
        host=host,
        port=443,
        version='vim.version.version6',
        path='/sdk',
        sslContext=context)

    si = vim.ServiceInstance("ServiceInstance", stub)
    content = si.RetrieveContent()
    content.sessionManager.Login(user, password, None)
    return si


def disconnect(si):
    content = si.RetrieveContent()
    content.sessionManager.Logout()


def equals_match(name, mor):
    LOG.debug('Check %s equals %s' % (mor.name, name))
    return name == mor.name


def regex_match(pattern, mor):
    LOG.debug('Check %s matches %s' % (mor.name, pattern))
    m = re.match(pattern, mor.name)
    return True if m else False


class ManagedObject(object):

    def __init__(self, si, mor):
        self.mor = mor
        self.si = si

    def _create_container_view(self, container, vim_type):
        vmgr = self.si.RetrieveContent().viewManager
        return vmgr.CreateContainerView(
            container=container,
            type=[vim_type],
            recursive=True)

    def _get_entities_by_name(self, cls, container, name, matcher):
        LOG.debug('Search %s %s under %s' %
                  (cls.VIM_CLS, name, container.name))
        entities = []
        invtvw = self._create_container_view(container, cls.VIM_CLS)
        for mor in invtvw.view:
            if matcher(name, mor):
                LOG.debug('Found %s (%s)' % (mor.name, mor._moId))
                entities.append(cls(self.si, mor))
        return entities

    def _get_entity_by_name(self, cls, container, name, matcher):
        LOG.debug('Search the first %s %s under %s' %
                  (cls.VIM_CLS, name, container.name))
        invtvw = self._create_container_view(container, cls.VIM_CLS)
        for mor in invtvw.view:
            if matcher(name, mor):
                LOG.debug('Found %s (%s)' % (mor.name, mor._moId))
                return cls(self.si, mor)

    def _destroy(self):
        LOG.info('Destroy %s' % self.name)
        destroy_task = self.mor.Destroy()
        task.WaitForTask(task=destroy_task, si=self.si)

    @property
    def name(self):
        return self.mor.name

    @property
    def moid(self):
        return self.mor._moId

    def __getattr__(self, name):
        return getattr(self.mor, name)


class VirtualCenter(ManagedObject):

    def __enter__(self):
        self.si = connect(self.host, self.user, self.pwd)
        return self

    def __exit__(self, *exc_info):
        self.disconnect()

    def __init__(self, host, user, pwd):
        self.host = host
        self.user = user
        self.pwd = pwd
        self.si = None

    def disconnect(self):
        if self.si is not None:
            disconnect(self.si)
            self.si = None

    def requires_connection(func):
        """Decorator that makes sure that we have active connection to virtual

        center
        @param func: method that is decorated
        @return: return decorator
        """

        def connect_me(self, *args, **kargs):
            if self.si is None:
                self.si = connect(self.host, self.user, self.pwd)
            return func(self, *args, **kargs)
        return connect_me

    def _get_root_folder(self):
        return self.si.RetrieveContent().rootFolder

    @requires_connection
    def create_datacenter(self, name):
        """Creates a datacenter in the root folder.

        @param name: name of the datacenter
        @return returns Datacenter instance
        """
        root_folder = self._get_root_folder()
        dc = root_folder.CreateDatacenter(name)
        return Datacenter(self.si, dc)

    @requires_connection
    def get_datacenter(self, name):
        """Returns a reference to datacenter in the root folder.

        @param name: name of the datacenter
        @return returns Datacenter instance
        """
        root_folder = self._get_root_folder()
        for mor in root_folder.childEntity:
            if name == mor.name:
                return Datacenter(self.si, mor)

    @requires_connection
    def get_hosts(self):
        vmgr = self.si.RetrieveContent().viewManager
        invtvw = vmgr.CreateContainerView(
            container=self._get_root_folder(),
            type=[vim.HostSystem],
            recursive=True)
        return [Host(self.si, h) for h in invtvw.view]

    @requires_connection
    def get_log_bundle(self):
        def get_all_host_systems():
            vmgr = self.si.RetrieveContent().viewManager
            invtvw = vmgr.CreateContainerView(
                container=self._get_root_folder(),
                type=[vim.HostSystem],
                recursive=True)
            return [h for h in invtvw.view]

        content = self.si.RetrieveContent()
        dmgr = content.diagnosticManager
        generate_task = dmgr.GenerateLogBundles_Task(
            includeDefault=True,
            host=get_all_host_systems())
        task.WaitForTask(generate_task, self.si)
        bundles = [b.url.replace("*", self.host)
                   for b in generate_task.info.result]
        return bundles

    @requires_connection
    def get_entities_by_name(self, cls, name):
        """Recursively search entities by name.

        :param cls:  ManagedObject sub class.
        :param name: entity name.
        :returns: a list of entities. Empty list if nothing found.
        """
        return self._get_entities_by_name(cls, self._get_root_folder(), name,
                                          equals_match)

    @requires_connection
    def get_entity_by_name(self, cls, name):
        """Recursively search entity by name.

        :param cls:  ManagedObject sub class.
        :param name: entity name.
        :returns: first found entity. None if nothing found.
        """
        return self._get_entity_by_name(cls, self._get_root_folder(), name,
                                        equals_match)

    @requires_connection
    def get_entities_by_regex(self, cls, regex):
        """Recursively search entities by regular expression.

        :param cls:  ManagedObject sub class.
        :param regex: regular expression to match entity name.
        :returns: a list of entities. Empty list if nothing found.
        """
        return self._get_entities_by_name(cls, self._get_root_folder(), regex,
                                          regex_match)

    @requires_connection
    def get_entity_by_regex(self, cls, regex):
        """Recursively search entity by regular expression.

        :param cls:  ManagedObject sub class.
        :param regex: regular expression to match entity name.
        :returns: first found entity. None if nothing found.
        """
        return self._get_entity_by_name(cls, self._get_root_folder(), regex,
                                        regex_match)

    @requires_connection
    def query_vpx_settings(self, name):
        """Query options in the option hierarchy tree. Return an
        vim.option.OptionValue list.

        :param name: key of the vpx setting.
        """
        try:
            option_values = \
                self.si.RetrieveContent().setting.QueryOptions(name)
        except vim.fault.InvalidName:
            option_values = []
            LOG.debug('Option %s not Found in VpxSetting.', name)
        return option_values

    @requires_connection
    def update_vpx_settings(self, settings):
        """Update options in the option hierarchy tree.

        :param settings: key value map of the vpx setting.
        """
        LOG.debug('Update VpxSettings: %s', settings)
        option_values = []
        for name in settings:
            option_values.append(vim.option.OptionValue(key=name,
                                                        value=settings[name]))
        return self.si.RetrieveContent().setting.UpdateOptions(option_values)


class Datacenter(ManagedObject):
    VIM_CLS = vim.Datacenter

    def __init__(self, si, dc):
        if not isinstance(dc, Datacenter.VIM_CLS):
            raise TypeError("Not a vim.Datacenter object")
        super(Datacenter, self).__init__(si, dc)

    def create_cluster(self, name, config=vim.cluster.ConfigSpecEx()):
        """Creates cluster.

        @param name: name of the cluster
        @param config: vim.cluster.ConfigSpecEx
        """

        hostFolder = self.mor.hostFolder
        c = hostFolder.CreateClusterEx(name, config)
        return Cluster(self.si, c)

    def get_cluster(self, name):
        for mor in self.mor.hostFolder.childEntity:
            if isinstance(mor, vim.ClusterComputeResource) \
                    and name == mor.name:
                return Cluster(self.si, mor)

    def create_dvs(self, spec):
        dvs_task = self.mor.networkFolder.CreateDVS_Task(spec)
        task.WaitForTask(task=dvs_task, si=self.si)

        return DistributedVirtualSwitch(self.si, dvs_task.info.result)

    def get_entities_by_name(self, cls, name):
        """Recursively search entities by name.

        :param cls:  ManagedObject sub class.
        :param name: entity name.
        :returns: a list of entities. Empty list if nothing found.
        """
        return self._get_entities_by_name(cls, self.mor, name, equals_match)

    def get_entity_by_name(self, cls, name):
        """Recursively search entity by name.

        :param cls:  ManagedObject sub class.
        :param name: entity name.
        :returns: first found entity. None if nothing found.
        """
        return self._get_entity_by_name(cls, self.mor, name, equals_match)

    def get_entities_by_regex(self, cls, regex):
        """Recursively search entities by regular expression.

        :param cls:  ManagedObject sub class.
        :param regex: regular expression to match entity name.
        :returns: a list of entities. Empty list if nothing found.
        """
        return self._get_entities_by_name(cls, self.mor, regex, regex_match)

    def get_entity_by_regex(self, cls, regex):
        """Recursively search entity by regular expression.

        :param cls:  ManagedObject sub class.
        :param regex: regular expression to match entity name.
        :returns: first found entity. None if nothing found.
        """
        return self._get_entity_by_name(cls, self.mor, regex, regex_match)


class Cluster(ManagedObject):
    VIM_CLS = vim.ClusterComputeResource

    def __init__(self, si, cluster):
        if not isinstance(cluster, Cluster.VIM_CLS):
            raise TypeError("Not a vim.ClusterComputeResource object")
        super(Cluster, self).__init__(si, cluster)

    def add_host(self, hostConnectSpec):
        """Adds host to a cluster.

        @param hostConnectSpec: vim.host.ConnectSpec
        """

        hosttask = self.mor.AddHost_Task(
            spec=hostConnectSpec,
            asConnected=True)
        task.WaitForTask(task=hosttask, si=self.si)

    def enable_drs(self, enable=True):
        spec = vim.cluster.ConfigSpec(
            drsConfig=vim.cluster.DrsConfigInfo(enabled=enable))
        rcfg_task = self.mor.ReconfigureCluster_Task(
            spec=spec, modify=True)
        task.WaitForTask(task=rcfg_task, si=self.si)


class Host(ManagedObject):
    VIM_CLS = vim.HostSystem

    def __init__(self, si, host_system):
        if not isinstance(host_system, Host.VIM_CLS):
            raise TypeError("Not a vim.HostSystem object")
        super(Host, self).__init__(si, host_system)

    def remove_datastore(self, datastore):
        """Remove datastore of the host.

        :param datastore: Datastore object.
        """
        LOG.info('Remove datastore %s from host %s', datastore.name, self.name)
        self.mor.configManager.datastoreSystem.RemoveDatastore(datastore.mor)


class VM(ManagedObject):
    VIM_CLS = vim.VirtualMachine

    def __init__(self, si, vm):
        if not isinstance(vm, VM.VIM_CLS):
            raise TypeError("Not a vim.VirtualMachine object")
        super(VM, self).__init__(si, vm)

    @property
    def ip(self):
        return self.mor.summary.guest.ipAddress

    def add_nic(self, network):
        """Add a nic and connect to network.

        :param network: Network or DistributedVirtualPortgroup
        """
        LOG.info('Add network %s to VM %s' % (network.name, self.name))
        devices = []
        nicspec = vim.vm.device.VirtualDeviceSpec()

        nicspec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
        # For now hard code change it to to use string nic_type
        nicspec.device = vim.vm.device.VirtualVmxnet3()
        nicspec.device.wakeOnLanEnabled = True
        nicspec.device.deviceInfo = vim.Description()

        net_mor = network.mor
        if isinstance(net_mor, vim.dvs.DistributedVirtualPortgroup):
            # Configuration for DVPortgroups
            dvs_port_connection = vim.dvs.PortConnection()
            dvs_port_connection.portgroupKey = net_mor.key
            dvs_port_connection.switchUuid = net_mor.config.\
                distributedVirtualSwitch.uuid
            nicspec.device.backing = vim.vm.device.VirtualEthernetCard.\
                DistributedVirtualPortBackingInfo()
            nicspec.device.backing.port = dvs_port_connection
        else:
            # Configuration for Standard switch port groups
            nicspec.device.backing = vim.vm.device.\
                VirtualEthernetCard.NetworkBackingInfo()
            nicspec.device.backing.network = net_mor
            nicspec.device.backing.deviceName = net_mor.name

        nicspec.device.connectable = vim.vm.device.VirtualDevice.ConnectInfo()
        nicspec.device.connectable.startConnected = True
        nicspec.device.connectable.allowGuestControl = True

        devices.append(nicspec)
        vmconf = vim.vm.ConfigSpec(deviceChange=devices)

        reconfig_task = self.mor.ReconfigVM_Task(vmconf)
        task.WaitForTask(task=reconfig_task, si=self.si)

    def get_state(self):
        state = self.mor.runtime.powerState
        return state

    def poweroff(self):
        LOG.info('Power off %s' % self.name)
        poweroff_task = self.mor.PowerOff()
        task.WaitForTask(task=poweroff_task, si=self.si)

    def destroy(self):
        self._destroy()


class DataStore(ManagedObject):
    VIM_CLS = vim.Datastore

    def __init__(self, si, ds):
        if not isinstance(ds, DataStore.VIM_CLS):
            raise TypeError("Not a vim.Datastore object")
        super(DataStore, self).__init__(si, ds)


class DistributedVirtualSwitch(ManagedObject):
    VIM_CLS = vim.VmwareDistributedVirtualSwitch

    def __init__(self, si, dvs):
        if not isinstance(dvs, DistributedVirtualSwitch.VIM_CLS):
            raise TypeError("Not a vim.VmwareDistributedVirtualSwitch object")
        super(DistributedVirtualSwitch, self).__init__(si, dvs)


class DistributedVirtualPortgroup(ManagedObject):
    VIM_CLS = vim.DistributedVirtualPortgroup

    def __init__(self, si, dvpg):
        if not isinstance(dvpg, DistributedVirtualPortgroup.VIM_CLS):
            raise TypeError("Not a vim.DistributedVirtualPortgroup object")
        super(DistributedVirtualPortgroup, self).__init__(si, dvpg)


class Network(ManagedObject):
    VIM_CLS = vim.Network

    def __init__(self, si, net):
        if not isinstance(net, Network.VIM_CLS):
            raise TypeError("Not a vim.Network object")
        super(Network, self).__init__(si, net)

    def destroy(self):
        self._destroy()


class Folder(ManagedObject):
    VIM_CLS = vim.Folder

    def __init__(self, si, folder):
        if not isinstance(folder, Folder.VIM_CLS):
            raise TypeError("Not a vim.Folder object")
        super(Folder, self).__init__(si, folder)

    def destroy(self):
        self._destroy()


class Vapp(ManagedObject):
    VIM_CLS = vim.VirtualApp

    def __init__(self, si, vapp):
        if not isinstance(vapp, Vapp.VIM_CLS):
            raise TypeError("Not a vim.VirtualApp object")
        super(Vapp, self).__init__(si, vapp)

    def poweroff(self):
        LOG.info('Power off %s' % self.name)
        poweroff_task = self.mor.PowerOff(force=True)
        task.WaitForTask(task=poweroff_task, si=self.si)

    def destroy(self):
        self._destroy()

    def get_state(self):
        state = self.mor.summary.vAppState
        return state

    def poweron(self):
        LOG.info('Power on %s' % self.name)
        poweron_task = self.mor.PowerOn()
        task.WaitForTask(task=poweron_task, si=self.si)

    @property
    def version(self):
        return self.mor.summary.product.fullVersion
