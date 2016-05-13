import logging
import json
import os

import oms_utils
import cluster_utils
import build_utils
from omsclient.oms_controller import OmsController
from sshutil.remote import RemoteClient


LOG = logging.getLogger(__name__)


class Setup(object):
    def __init__(self, **kwargs):
        pass


class Openstack(Setup):
    def __init__(self, vc_host, vc_user=None, vc_pwd=None, datacenter=None,
                 cluster=None, datastore=None, build_id=None):
        self.vc_host = vc_host
        self.vc_user = vc_user
        self.vc_pwd = vc_pwd
        self.datacenter = datacenter
        self.cluster = cluster
        self.datastore = datastore
        self.build_id = build_id
        self.version = None

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
                                  build_id=oms_spec['build'])
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
        self.ova_path = ova_path if ova_path else \
            build_utils.get_ova_url(self.build_id)
        self.vapp_name = os.path.basename(self.ova_path).replace('.ova', '')
        self.cluster_spec = cluster_spec

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
        self.oms_ctl = OmsController(self.oms_ip, self.vc_user, self.vc_pwd)

    def get_version(self):
        if not self.version:
            self.version = oms_utils.get_vapp_version(self.vc_host,
                                                      self.vc_user,
                                                      self.vc_pwd,
                                                      self.vapp_name)
        return self.version

    def is_running(self):
        try:
            return cluster_utils.check_cluster_status(self.oms_ctl,
                                                      ['RUNNING'])
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
        if not self.is_running():
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
            except Exception:
                self.get_support_bundle()
                raise
        else:
            LOG.info('OpenStack cluster already exists and is running. '
                     'Skip creating OpenStack cluster.')

    def get_support_bundle(self):
        name = self.cluster_spec['name'] if self.cluster_spec else 'VIO'
        spec = {"deployment_name": name}
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
        ssh_client = RemoteClient(self.oms_ip, self.oms_user, self.oms_pwd)
        file_name = os.path.basename(patch_file)
        remote_path = os.path.join('/tmp', file_name)
        ssh_client.scp(patch_file, '/tmp')
        try:
            oms_utils.apply_patch(self.oms_ip, remote_path, self.oms_user,
                                  self.oms_pwd)
        except Exception:
            self.get_support_bundle()
            raise


class Devstack(Openstack):
    def __init__(self):
        raise NotImplementedError

    def deploy_openstack(self, config_spec):
        raise NotImplementedError
