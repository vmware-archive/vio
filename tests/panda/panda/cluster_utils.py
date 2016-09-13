import json
import logging
import re
import ssl

from M2Crypto import X509
from exceptions import ProvisionError
from exceptions import NotCompletedError
from exceptions import NotFoundError
from pyVmomiwrapper.vmwareapi import VirtualCenter
from pyVmomiwrapper.vmwareapi import DataStore
from pyVmomiwrapper.vmwareapi import DistributedVirtualSwitch


LOG = logging.getLogger(__name__)
DVS_BACKEND = 'dvs'
NSXV_BACKEND = 'nsxv'
NSXT_BACKEND = 'nsxt'
VCENTER_PORT = 443
LDAP_BACKEND = 'ldap'


def get_nodegroup_by_name(cluster_spec, name):
    for node_group in cluster_spec['nodeGroups']:
        if node_group['name'] == name:
            return node_group


def get_nodegroup_by_role(cluster_spec, role):
    for node_group in cluster_spec['nodeGroups']:
        roles = node_group.get('roles') or [node_group['role']]
        if role in roles:
            return node_group


def get_neutron_backend(cluster_spec):
    controller = get_nodegroup_by_role(cluster_spec, 'Controller')
    return controller['attributes']['neutron_backend']


def create_deployment_plan(oms_ctl, cluster_spec):
    LOG.info('Create OpenStack cluster deployment plan.')
    # This is a workaround due to oms api design inconsistency.
    data_network = cluster_spec['networkConfig']['DATA_NETWORK']
    controller = get_nodegroup_by_role(cluster_spec, 'Controller')
    if DVS_BACKEND == controller['attributes']['neutron_backend']:
        cluster_spec['networkConfig']['DATA_NETWORK'] = \
            cluster_spec['networkConfig']['MGT_NETWORK']
    spec_str = json.dumps(cluster_spec)
    resp = oms_ctl.create_deployment_plan(spec_str)
    if resp.status_code == 200:
        LOG.debug("Deployment plan: %s" % resp.text)
        cluster_spec['attributes']['plan'] = resp.text
    else:
        LOG.error("Failed to create deployment plan!")
        raise ProvisionError("Failed to create deployment plan!")
    if DVS_BACKEND == controller['attributes']['neutron_backend']:
        cluster_spec['networkConfig']['DATA_NETWORK'] = data_network
    return cluster_spec


def delete_cluster(oms_ctl, name="VIO"):
    LOG.info('Deleting Openstack cluster %s' % name)
    oms_ctl.delete_deployment(name)


def check_creation_completed(oms_ctl, cluster_name):
    if not check_cluster_status(oms_ctl, cluster_name,
                                ["RUNNING", "PROVISION_ERROR"]):
        raise NotCompletedError("Provisioning is not completed")


def get_cluster(oms_ctl, cluster_name):
    clusters = oms_ctl.list_deployments().json()
    for cluster in clusters:
        if cluster['name'] == cluster_name:
            return cluster
    raise NotFoundError('Cluster %s not Found.' % cluster_name)


def get_private_vip(oms_ctl, cluster_name):
    cluster = get_cluster(oms_ctl, cluster_name)
    load_balance = get_nodegroup_by_role(cluster, 'LoadBalancer')
    private_vip = load_balance['attributes']['internal_vip']
    LOG.debug('Private VIP: %s' % private_vip)
    return private_vip


def get_node_error(oms_ctl, cluster_name):
    cluster = get_cluster(oms_ctl, cluster_name)
    groups = cluster['nodeGroups']
    for group in groups:
        for instance in group['instances']:
            if instance['status'] == 'Bootstrap Failed':
                return 'Ansible error'
    return 'OMS java error'


def check_cluster_status(oms_ctl, cluster_name, status_list):
    cluster = get_cluster(oms_ctl, cluster_name)
    status = cluster['status']
    LOG.debug('Cluster status: %s' % status)
    if status in status_list:
        return True
    return False


def create_openstack_cluster(oms_ctl, cluster_spec):
    LOG.info('Start to create OpenStack Cluster.')
    try:
        oms_ctl.create_deployment_by_spec(cluster_spec)
    except Exception:
        LOG.exception('Creating cluster error.')
    if check_cluster_status(oms_ctl, cluster_spec['name'], ['RUNNING']):
        LOG.info('Successfully deployed OpenStack Cluster.')
    else:
        LOG.error('Openstack cluster status is not running!')
        cause = get_node_error(oms_ctl, cluster_spec['name'])
        LOG.error('Detected %s' % cause)
        raise ProvisionError(cause)


def get_vc_fingerprint(vcenter_ip):
    cert_pem = ssl.get_server_certificate((vcenter_ip, VCENTER_PORT),
                                          ssl_version=ssl.PROTOCOL_TLSv1)
    x509 = X509.load_cert_string(cert_pem, X509.FORMAT_PEM)
    fp = x509.get_fingerprint('sha1')
    return ':'.join(a+b for a, b in zip(fp[::2], fp[1::2]))


def add_compute_vc(oms_ctl, ssh_client, vcenter_insecure, vcenter_ip, user,
                   password):
    LOG.info('Add compute VC %s.', vcenter_ip)
    fp = get_vc_fingerprint(vcenter_ip)
    if vcenter_insecure == 'false' and \
            re.match(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', vcenter_ip):
        vc_host = get_fqdn(ssh_client, vcenter_ip)
    else:
        vc_host = vcenter_ip
    spec = {'hostname': vc_host,
            'port': VCENTER_PORT,
            'username': user,
            'password': password,
            'thumbprint': fp}
    LOG.debug("Spec of compute VC: %s" % spec)
    resp = oms_ctl.add_compute_vc(spec)
    if resp.status_code != 200:
        raise ProvisionError('Failed to add compute cluster. Spec: %s' % spec)


def get_cluster_moid(vc_host, vc_user, vc_pwd, datacenter, cluster):
    with VirtualCenter(vc_host, vc_user, vc_pwd) as vc:
        dc_mor = vc.get_datacenter(datacenter)
        return dc_mor.get_cluster(cluster).moid


def get_moids(vc_host, vc_user, vc_pwd, datacenter, mgmt_cluster,
              compute_clusters, datastore):
    with VirtualCenter(vc_host, vc_user, vc_pwd) as vc:
        dc_mor = vc.get_datacenter(datacenter)
        mgmt_moid = dc_mor.get_cluster(mgmt_cluster).moid
        compute_moids = []
        for compute in compute_clusters:
            compute_moids.append(dc_mor.get_cluster(compute).moid)
        ds_moid = dc_mor.get_entity_by_name(DataStore, datastore).moid

        return mgmt_moid, compute_moids, ds_moid


def _set_compute_driver(compute_group, compute_morefs, vcenter_ip=None):
    node_attributes = compute_group['nodeAttributes']
    count = 0
    for attribute in node_attributes:
        # This is very bad design since cluster_moid is different format in
        # multiple and single VC
        if 'vcenter_ip' in attribute:
            attribute['vcenter_ip'] = vcenter_ip
        attribute['cluster_moid'] = compute_morefs[count]
        count += 1


def refresh_nsxv_config(cluster_spec, nsxv_ip, nsxv_user, nsxv_pwd):
    ctl_attrs = get_controller_attrs(cluster_spec)
    ctl_attrs['nsxv_manager'] = nsxv_ip
    ctl_attrs['nsxv_username'] = nsxv_user
    ctl_attrs['nsxv_password'] = nsxv_pwd


def refresh_mgmt_moid(cluster_spec, vc_host, vc_user, vc_pwd, datacenter,
                      mgmt_cluster):
    with VirtualCenter(vc_host, vc_user, vc_pwd) as vc:
        dc_mor = vc.get_datacenter(datacenter)
        mgmt_cls_moid = dc_mor.get_cluster(mgmt_cluster).moid
    LOG.debug('Management dc: %s, MOID: %s', datacenter, dc_mor.moid)
    LOG.debug('Management cluster: %s, MOID: %s', mgmt_cluster, mgmt_cls_moid)
    # Set management cluster mo id.
    cluster_spec['vcClusters'][0]['moid'] = mgmt_cls_moid


def refresh_nodegroup_nsxv_moid(cluster_spec, vc_host, vc_user, vc_pwd,
                                datacenter, compute_clusters, glance_ds,
                                nsxv_edge_dvs, nsxv_edge_cluster):
    ctl_attrs = get_controller_attrs(cluster_spec)
    with VirtualCenter(vc_host, vc_user, vc_pwd) as vc:
        dc_mor = vc.get_datacenter(datacenter)
        LOG.debug('Compute dc: %s, MOID: %s', datacenter, dc_mor.moid)
        compute_moids = []
        for compute in compute_clusters:
            cls_moid = dc_mor.get_cluster(compute).moid
            LOG.debug('Compute cluster: %s, MOID: %s', compute, cls_moid)
            compute_moids.append(cls_moid)
        edge_dvs_moid = dc_mor.get_entity_by_name(DistributedVirtualSwitch,
                                                  nsxv_edge_dvs).moid
        LOG.debug('Edge dvs: %s, MOID: %s', nsxv_edge_dvs, edge_dvs_moid)
        edge_cluster_moid = dc_mor.get_cluster(nsxv_edge_cluster).moid
        LOG.debug('Edge cluster: %s, MOID: %s', nsxv_edge_cluster,
                  edge_cluster_moid)
        # This is very bad design in cluster spec, only multiple VCs need to
        # get glance ds mo id and set it like "null:Datastore:datastore-12". In
        # single VC, ds name is used "vio-datacenter:vdnetSharedStorage:100".
        if glance_ds:
            glance_ds_moid = dc_mor.get_entity_by_name(DataStore,
                                                       glance_ds).moid
            LOG.debug('Glance ds: %s, MOID: %s', glance_ds, glance_ds_moid)
            ctl_attrs['glance_datastores'] = 'null:Datastore:%s' % \
                                             glance_ds_moid
    # Set controller group
    ctl_attrs['nsxv_edge_cluster_moref'] = edge_cluster_moid
    ctl_attrs['nsxv_dvs_moref'] = edge_dvs_moid
    # Set compute driver group
    compute_group = get_nodegroup_by_role(cluster_spec, 'Compute')
    _set_compute_driver(compute_group, compute_moids, vc_host)


def refresh_nodegroup_dvs_moid(cluster_spec, vc_host, vc_user, vc_pwd,
                               datacenter, compute_clusters, dvs):
    with VirtualCenter(vc_host, vc_user, vc_pwd) as vc:
        dc_mor = vc.get_datacenter(datacenter)
        compute_moids = []
        for compute in compute_clusters:
            cls_moid = dc_mor.get_cluster(compute).moid
            LOG.debug('Compute cluster: %s, MOID: %s', compute, cls_moid)
            compute_moids.append(cls_moid)
    # Set controller group
    ctl_attrs = get_controller_attrs(cluster_spec)
    ctl_attrs['dvs_default_name'] = dvs
    # Set compute driver group
    compute_group = get_nodegroup_by_role(cluster_spec, 'Compute')
    _set_compute_driver(compute_group, compute_moids)


def refresh_vc_config(cluster_spec, vc_host, vc_user, vc_pwd):
    ctl_attrs = get_controller_attrs(cluster_spec)
    ctl_attrs['vcenter_ip'] = vc_host
    ctl_attrs['vcenter_user'] = vc_user
    ctl_attrs['vcenter_password'] = vc_pwd


def set_vc_fqdn(cluster_spec, ssh_client):
    ctl_attrs = get_controller_attrs(cluster_spec)
    vc_host = ctl_attrs['vcenter_ip']
    if ctl_attrs.get('vcenter_insecure', '') == 'false' and re.match(
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', ctl_attrs['vcenter_ip']):
        fqdn = get_fqdn(ssh_client, vc_host)
        LOG.debug('vCenter IP: %s, change it to FQDN: %s', vc_host, fqdn)
        ctl_attrs['vcenter_ip'] = fqdn
        for compute in get_nodegroup_by_role(
                cluster_spec, 'Compute')['nodeAttributes']:
            if 'vcenter_ip' in compute:
                compute['vcenter_ip'] = fqdn


def get_fqdn(ssh_client, vc_host):
    return ssh_client.run('python -c \'import socket; print socket.getfqdn'
                          '("%s")\'' % vc_host).replace('\n', '')


def refresh_syslog_tag(cluster_spec, build_id):
    ctl_attrs = get_controller_attrs(cluster_spec)
    if 'syslog_server_tag' in ctl_attrs:
        if ctl_attrs['neutron_backend'] == NSXV_BACKEND:
            ctl_attrs['syslog_server_tag'] = 'NSXV-%s' % build_id
        else:
            ctl_attrs['syslog_server_tag'] = 'DVS-%s' % build_id


def get_controller_attrs(cluster_spec):
    return get_nodegroup_by_role(cluster_spec, 'Controller')['attributes']


def upgrade(oms_ctl, blue_name, green_name, spec):
    LOG.info('Start to upgrade VIO cluster.')
    # Create green cluster
    LOG.debug('Create green cluster %s', green_name)
    oms_ctl.upgrade_provision(blue_name, spec)
    # Migrate data
    LOG.debug('Migrate data from cluster: %s', blue_name)
    oms_ctl.upgrade_migrate_data(blue_name)
    # Switch to green cluster
    LOG.debug('Switch from cluster: %s', blue_name)
    oms_ctl.upgrade_switch_to_green(blue_name)
    if not check_cluster_status(oms_ctl, green_name, ['RUNNING']):
        raise ProvisionError('Upgrading VIO cluster failed.')
    LOG.info('Successfully upgraded VIO cluster.')


def get_compute_cluster_moids(cluster_spec):
    compute_group = get_nodegroup_by_role(cluster_spec, 'Compute')
    instances = compute_group['instances']
    moids = list()
    for instance in instances:
        moids.append(instance['attributes']['cluster_moid'])
    return moids
