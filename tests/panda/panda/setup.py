import logging
import json
import os

import oms_utils
import cluster_utils
import build_utils
from omsclient.oms_controller import OmsController
from sshutil.remote import RemoteClient
from os_utils import enable_ldap_admin
from shellutil import shell


LOG = logging.getLogger(__name__)


class Setup(object):
    def __init__(self, **kwargs):
        pass


class Openstack(Setup):
    def __init__(self, vc_host, vc_user=None, vc_pwd=None, datacenter=None,
                 cluster=None, datastore=None, build_id=None, version=None):
        self.vc_host = vc_host
        self.vc_user = vc_user
        self.vc_pwd = vc_pwd
        self.datacenter = datacenter
        self.cluster = cluster
        self.datastore = datastore
        self.build_id = build_id
        self.version = version

    def deploy_openstack(self, config_spec):
        raise NotImplementedError


class VIO(Openstack):
    def __init__(self, oms_spec, cluster_spec, log_dir):
        super(VIO, self).__init__(oms_spec['vc_host'],
                                  vc_user=oms_spec['vc_user'],
                                  vc_pwd=oms_spec['vc_password'],
                                  datacenter=oms_spec['datacenter'],
                                  cluster=oms_spec['cluster'],
                                  datastore=oms_spec['datastore'],
                                  build_id=oms_spec['build'],
                                  version=oms_spec.get('version', None))
        self.oms_ip = oms_spec['host_ip']
        self.oms_netmask = oms_spec['netmask']
        self.oms_gateway = oms_spec['gateway']
        self.oms_dns = oms_spec.get('dns', None)
        self.oms_ntp = oms_spec.get('ntp_server', None)
        self.oms_ctl = None
        self.oms_network = oms_spec['network']
        self.oms_user = oms_spec['username']
        self.oms_pwd = oms_spec['password']
        self.log_dir = log_dir if os.path.isabs(log_dir) else \
            os.path.abspath(log_dir)
        ova_path = oms_spec.get('ova_path', '').strip()
        if ova_path:
            self.remove_ova = False
            self.ova_path = ova_path
        else:
            self.remove_ova = True
            self.ova_path = build_utils.download_ova(self.build_id)
        self.vapp_name = os.path.basename(self.ova_path).replace('.ova', '')
        self.cluster_spec = cluster_spec
        self.omjs_properties = oms_spec.get('omjs_properties', {})
        self.upgrade_index = 1
        self.cluster_name = cluster_spec['name'] if cluster_spec else 'VIO'
        if 'compute_vc_host' in oms_spec:
            self.compute_vc_host = oms_spec['compute_vc_host']
            self.compute_vc_user = oms_spec['compute_vc_user']
            self.compute_vc_pwd = oms_spec['compute_vc_password']
            self.compute_datacenter = oms_spec['compute_datacenter']
        else:
            self.compute_vc_host = self.vc_host
            self.compute_vc_user = self.vc_user
            self.compute_vc_pwd = self.vc_pwd
            self.compute_datacenter = self.datacenter

    def deploy_vapp(self):
        if not oms_utils.check_vapp_exists(self.vc_host, self.vc_user,
                                           self.vc_pwd, self.vapp_name):
            oms_utils.deploy_vapp(vc_host=self.vc_host,
                                  vc_user=self.vc_user,
                                  vc_password=self.vc_pwd,
                                  dc=self.datacenter,
                                  cluster=self.cluster,
                                  ds=self.datastore,
                                  network=self.oms_network,
                                  ova_path=self.ova_path,
                                  ntp_server=self.oms_ntp,
                                  viouser_pwd=self.oms_pwd,
                                  log_path=self.log_dir,
                                  ip=self.oms_ip,
                                  netmask=self.oms_netmask,
                                  gateway=self.oms_gateway,
                                  dns=self.oms_dns)
        else:
            LOG.info('VIO vApp already exists. Skip deploying vApp.')
        # Remove downloaded ova
        if self.remove_ova:
            shell.local('rm -f %s' % self.ova_path)
        self.oms_ctl = OmsController(self.oms_ip, self.vc_user, self.vc_pwd)

    def upgrade(self, public_vip, private_vip=None):
        blue_name = self.cluster_name
        self.cluster_name = 'UPGRADE%s' % self.upgrade_index
        if self.is_deployed(self.cluster_name):
            LOG.info('Cluster %s exists, skip upgrading.', self.cluster_name)
        else:
            oms_utils.wait_for_mgmt_service(self.oms_ip, self.vc_host,
                                            self.vc_pwd)
            # Write back the same omjs properties since b2b patch overwrite
            # them.
            self.config_omjs(self.omjs_properties)
            if int(self.get_version()[0]) >= 3:
                attributes = cluster_utils.get_controller_attrs(
                    self.cluster_spec)
                admin_user = attributes['admin_user']
                admin_password = attributes['admin_password']
                spec = {'clusterName': self.cluster_name,
                        'public_vip': public_vip,
                        'admin_user': admin_user,
                        'admin_password': admin_password}
            else:
                spec = {'clusterName': self.cluster_name,
                        'publicVIP': public_vip,
                        'internalVIP': private_vip}
            try:
                cluster_utils.upgrade(self.oms_ctl, blue_name,
                                      self.cluster_name, spec)
            except Exception:
                self.get_support_bundle()
                raise
        self.upgrade_index += 1
        return cluster_utils.get_cluster(self.oms_ctl, self.cluster_name)

    def get_version(self):
        if not self.version:
            self.version = oms_utils.get_vapp_version(self.vc_host,
                                                      self.vc_user,
                                                      self.vc_pwd,
                                                      self.vapp_name)[0:5]
        return self.version

    def is_deployed(self, cluster_name):
        try:
            return cluster_utils.check_cluster_status(self.oms_ctl,
                                                      cluster_name,
                                                      ['RUNNING', 'STOPPED'])
        except Exception, error:
            LOG.debug('Failed to retrieve VIO cluster status: %s' % error)
            return False

    def config_omjs(self, properties):
        oms_utils.config_omjs(ip=self.oms_ip,
                              vc_user=self.vc_user,
                              vc_password=self.vc_pwd,
                              properties=properties,
                              user=self.oms_user,
                              password=self.oms_pwd)
        self.oms_ctl = OmsController(self.oms_ip, self.vc_user, self.vc_pwd)

    def deploy_openstack(self):
        if not self.is_deployed(self.cluster_name):
            # TODO(xiaoy): Remove provision failed cluster
            # Add compute VC if multiple VC
            attrs = cluster_utils.get_controller_attrs(self.cluster_spec)
            ssh_client = RemoteClient(self.oms_ip, self.oms_user, self.oms_pwd)
            if attrs['vcenter_ip'] != self.vc_host:
                LOG.debug('Managment VC: %s, Compute VC: %s. This is multi-vc',
                          self.vc_host, attrs['vcenter_ip'])
                cluster_utils.add_compute_vc(self.oms_ctl,
                                             ssh_client,
                                             attrs.get('vcenter_insecure', ''),
                                             attrs['vcenter_ip'],
                                             attrs['vcenter_user'],
                                             attrs['vcenter_password'])
            try:
                cluster_utils.set_vc_fqdn(self.cluster_spec, ssh_client)
                # Create plan when it is empty
                if not self.cluster_spec['attributes']['plan']:
                    self.cluster_spec = cluster_utils.create_deployment_plan(
                        self.oms_ctl, self.cluster_spec)
                cluster_utils.create_openstack_cluster(self.oms_ctl,
                                                       self.cluster_spec)
                if attrs['keystone_backend'] == cluster_utils.LDAP_BACKEND \
                        and int(self.get_version()[0]) >= 3:
                    private_vip = cluster_utils.get_private_vip(
                        self.oms_ctl, self.cluster_name)
                    enable_ldap_admin(private_vip=private_vip,
                                      local_user_name=attrs['admin_user'],
                                      local_user_pwd=attrs['admin_password'],
                                      ldap_user_name=attrs['ldap_user'])
            except Exception:
                self.get_support_bundle()
                raise
        else:
            LOG.info('Cluster %s already exists. Skip creating it.',
                     self.cluster_name)
        LOG.debug('Current VIO Version: %s', self.version)

    def get_support_bundle(self):
        spec = {"deployment_name": self.cluster_name}
        json_str = json.dumps(spec)
        try:
            # Rest client session always time out after tests
            self.oms_ctl.login()
            file_name = self.oms_ctl.get_support_bundle(json_str, self.log_dir)
            LOG.info('Downloaded support bundle to %s/%s.' %
                     (self.log_dir, file_name))
        except Exception as error:
            LOG.exception('Failed to get support bundle: %s' % error)

    def apply_patch(self, patch_file):
        try:
            patch_info = oms_utils.apply_patch(self.oms_ip, patch_file,
                                               self.oms_user, self.oms_pwd)
            self.version = patch_info['Version']
        except Exception:
            self.get_support_bundle()
            raise
        LOG.debug('Current VIO Version: %s', self.version)

    def add_compute_cluster(self, name):
        LOG.info('Add compute cluster: %s', name)
        cluster_moid = cluster_utils.get_cluster_moid(self.compute_vc_host,
                                                      self.compute_vc_user,
                                                      self.compute_vc_pwd,
                                                      self.compute_datacenter,
                                                      name)
        cluster_spec = cluster_utils.get_cluster(self.oms_ctl,
                                                 self.cluster_name)
        moids = cluster_utils.get_compute_cluster_moids(cluster_spec)
        if cluster_moid in moids:
            LOG.info('Cluster %s is already a compute cluster, skip adding '
                     'it.', name)
            return
        spec = [{
                    "cluster_name": name,
                    "datastore_regex": self.datastore,
                    "cluster_moid": cluster_moid
                }]
        try:
            self.oms_ctl.add_nova_node(self.cluster_name, "ComputeDriver",
                                       json.dumps(spec))
        except Exception:
            self.get_support_bundle()
            raise
        LOG.info('Cluster %s is added as a compute cluster.', name)


class Devstack(Openstack):
    def __init__(self):
        raise NotImplementedError

    def deploy_openstack(self, config_spec):
        raise NotImplementedError
