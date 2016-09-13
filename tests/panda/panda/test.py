import logging
import os
import json

import cluster_utils
from panda.exceptions import NotSupportedError
import tempest_utils
from cluster_utils import NSXT_BACKEND
from cluster_utils import NSXV_BACKEND
from cluster_utils import LDAP_BACKEND
from tempest_utils import LEGACY_PROVIDER
from tempest_utils import PRE_PROVISIONED_PROVIDER
from shellutil import shell
from omsclient.oms_controller import OmsController


LOG = logging.getLogger(__name__)
PASS = 0
FAIL = 1
VIO_LOGS_DIR = 'vio'
V1_DVS_BRANCH = 'dvs-1.0.0'
V2_DVS_BRANCH = 'dvs-2.0'


class Test(object):
    def __init__(self, test_name, log_dir, oms_spec, cluster_spec):
        self.test_name = test_name
        self.oms_spec = oms_spec
        self.cluster_spec = cluster_spec
        self.log_dir = log_dir if os.path.isabs(log_dir) else \
            os.path.abspath(log_dir)

    @staticmethod
    def run_tests(tests, log_dir, oms_spec, cluster_spec):
        results = PASS
        for test in tests.split(','):
            test = test.strip()
            if test in CLS_MAP.keys():
                cls = CLS_MAP.get(test)
                result = cls.run_test(test, log_dir, oms_spec, cluster_spec)
                if result != PASS:
                    results = FAIL
            else:
                raise Exception("Test %s not supported!" % test)
        return results

    @classmethod
    def run_test(cls, test, log_dir, oms_spec, cluster_spec):
        instance = cls(test, log_dir, oms_spec, cluster_spec)
        instance.set_up()
        instance.run()
        instance.clean_up()
        return instance.check_results()


class OMSAPI(Test):
    def __init__(self, test_name, log_dir, oms_spec, cluster_spec):
        super(OMSAPI, self).__init__(test_name, log_dir, oms_spec,
                                     cluster_spec)
        self.project_path = None

    def set_up(self):
        config = {
            "vc_ip": self.oms_spec['vc_host'],
            "vc_user": self.oms_spec['vc_user'],
            "vc_password": self.oms_spec['vc_password'],
            "vapp_name": '',
            "oms_ip": self.oms_spec['host_ip'],
            "oms_gateway": self.oms_spec['gateway'],
            "oms_netmask": self.oms_spec['netmask'],
            "oms_dns": self.oms_spec['dns'],
            "oms_network": '',
            "oms_dc": '',
            "oms_cluster": '',
            "oms_datastore": '',
            "nsxv_manager": self.oms_spec['nsxv_ip'],
            "nsxv_username": self.oms_spec['nsxv_user'],
            "nsxv_password": self.oms_spec['nsxv_password']
        }
        branch = self.oms_spec['version'][0:3]
        project_path = os.path.join(os.getcwd(), 'vio-api-test')
        if not os.path.exists(project_path):
            shell.local('git clone -b %s http://p3-review.eng.vmware.com/'
                        'vio-api-test' % branch)
        LOG.info('Install VIO OMS api test project in %s', project_path)
        shell.local('sudo pip install -r vio-api-test/requirements.txt')
        shell.local('sudo pip install -e vio-api-test/')
        config_path = "%s/vio/data/vio.vapp.json" % project_path
        LOG.info("Generate VIO OMS API test configuration to %s" % config_path)
        LOG.debug("vio.vapp.json: %s" % config)
        with open(config_path, 'w+') as fh:
            json.dump(config, fh, indent=2, separators=(',', ': '))
        self.project_path = project_path

    def _run(self, neutron_backend):
        report = '%s-nosetests.xml' % neutron_backend
        cmd = 'cd %s; python run_test.py -t %s --deployment_type %s ' \
              '--report %s' % (self.project_path, neutron_backend,
                               self.oms_spec['api_test_deployment_type'],
                               os.path.join(self.log_dir, report))
        LOG.info('[local] run: %s' % cmd)
        os.system(cmd)

    def run(self):
        LOG.info("oms-api tests begin.")
        self._run('dvs')
        self._run('nsxv')
        LOG.info("oms-api tests end.")
        # return result

    def check_results(self):
        # TODO (xiaoy): check if test fails in nosetests.xml
        return PASS

    def clean_up(self):
        pass


class Tempest(Test):
    def set_up(self):
        if not os.path.exists('tempest/included-tests.txt'):
            controller = cluster_utils.get_nodegroup_by_role(self.cluster_spec,
                                                             'Controller')
            admin_user = controller['attributes']['admin_user']
            admin_pwd = controller['attributes']['admin_password']
            neutron_backend = controller['attributes']['neutron_backend']
            keystone_backend = controller['attributes']['keystone_backend']
            admin_tenant = controller['attributes']['admin_tenant_name']
            ext_net_cidr = None
            ext_net_start_ip = None
            ext_net_end_ip = None
            ext_net_gateway = None
            nsx_manager = None
            nsx_user = None
            nsx_pwd = None
            if LDAP_BACKEND == keystone_backend:
                admin_user = self.oms_spec['openstack_admin']
                admin_pwd = self.oms_spec['openstack_admin_pwd']
            if neutron_backend == NSXV_BACKEND:
                nsx_manager = controller['attributes']['nsxv_manager']
                nsx_user = controller['attributes']['nsxv_username']
                nsx_pwd = controller['attributes']['nsxv_password']
            elif neutron_backend == NSXT_BACKEND:
                # TODO: get nsxt configure from spec
                pass
            if neutron_backend in [NSXV_BACKEND, NSXT_BACKEND]:
                ext_net_cidr = self.oms_spec['ext_net_cidr']
                ext_net_start_ip = self.oms_spec['ext_net_start_ip']
                ext_net_end_ip = self.oms_spec['ext_net_end_ip']
                ext_net_gateway = self.oms_spec['ext_net_gateway']
            creds_provider = self.oms_spec['openstack_creds_provider'].strip()
            if creds_provider in [LEGACY_PROVIDER, PRE_PROVISIONED_PROVIDER]:
                user1 = self.oms_spec['openstack_user1']
                user1_pwd = self.oms_spec['openstack_user1_pwd']
                user2 = self.oms_spec['openstack_user2']
                user2_pwd = self.oms_spec['openstack_user2_pwd']
            else:
                user1 = None
                user1_pwd = None
                user2 = None
                user2_pwd = None
            if 'compute_clusters' in self.oms_spec:
                min_compute_nodes = len(self.oms_spec['compute_clusters'])
            else:
                min_compute_nodes = 1
            tempest_utils.install_tempest()
            tempest_log_file = '%s/tempest.log' % self.log_dir
            oms_ctl = OmsController(self.oms_spec['host_ip'],
                                    self.oms_spec['vc_user'],
                                    self.oms_spec['vc_password'])
            private_vip = cluster_utils.get_private_vip(
                oms_ctl, self.cluster_spec['name'])
            if not private_vip:
                raise NotSupportedError('Can not get private VIP.')
            tempest_utils.config_tempest(private_vip=private_vip,
                                         admin_user=admin_user,
                                         admin_pwd=admin_pwd,
                                         neutron_backend=neutron_backend,
                                         creds_provider=creds_provider,
                                         default_user=user1,
                                         default_pwd=user1_pwd,
                                         alter_user=user2,
                                         alter_pwd=user2_pwd,
                                         ext_net_cidr=ext_net_cidr,
                                         ext_net_start_ip=ext_net_start_ip,
                                         ext_net_end_ip=ext_net_end_ip,
                                         ext_net_gateway=ext_net_gateway,
                                         tempest_log_file=tempest_log_file,
                                         admin_tenant=admin_tenant,
                                         min_compute_nodes=min_compute_nodes,
                                         nsx_manager=nsx_manager,
                                         nsx_user=nsx_user,
                                         nsx_pwd=nsx_pwd)
            shell.local('cp %s/etc/tempest.conf %s/' % (
                tempest_utils.TEMPEST_DIR, self.log_dir))
            tempest_utils.generate_run_list(neutron_backend)
        else:
            LOG.info('Tempest already exists. Skip setting up it.')

    def run(self):
        tempest_utils.run_test(self.test_name, self.log_dir)

    def check_results(self):
        # TODO (xiaoy): pass, rerun pass or fail
        return PASS

    def clean_up(self):
        pass


class VMwareTempest(Tempest):
    def set_up(self):
        if not os.path.exists('vmware_tempest/run-tests.txt'):
            super(VMwareTempest, self).set_up()
            tempest_utils.install_vmware_tempest()
            if 'compute_vc_host' in self.oms_spec:
                # Use compute VC in multi-VC setup.
                vc_host = self.oms_spec['compute_vc_host']
                vc_user = self.oms_spec['compute_vc_user']
                vc_password = self.oms_spec['compute_vc_password']
            else:
                vc_host = self.oms_spec['vc_host']
                vc_user = self.oms_spec['vc_user']
                vc_password = self.oms_spec['vc_password']
            tempest_utils.config_vmware_tempest(vc_host=vc_host,
                                                vc_user=vc_user,
                                                vc_password=vc_password)
            tempest_utils.generate_vmware_run_list()
        else:
            LOG.info('VMware tempest already exists. Skip setting up it.')

    def run(self):
        tempest_utils.run_vmware_test(self.log_dir)

    def check_results(self):
        return PASS

    def clean_up(self):
        pass

CLS_MAP = {'oms-api': OMSAPI,
           'vmware': VMwareTempest,
           'nova': Tempest,
           'cinder': Tempest,
           'neutron': Tempest,
           'heat': Tempest,
           'keystone': Tempest,
           'glance': Tempest,
           'scenario': Tempest,
           'nsxv': Tempest,
           'nsxt': Tempest}
