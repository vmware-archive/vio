import logging
import time

from setup import VIO
from test import Test
from test import PASS


LOG = logging.getLogger(__name__)


def vio_orchestration(oms_spec, log_dir, cluster_spec=None, tests=None):
    """ VIO end to end CI orchestration layer.
    Deploy vApp, create OpenStack cluster and run various tests.

    :param oms_spec: oms spec dict, see below sample.
    {
        "build": "3037963",
        "ova_path": "",
        "username": "viouser",
        "password": "vmware",
        "host_ip": "192.168.111.151",
        "gateway": "192.168.111.1",
        "netmask": "255.255.255.0",
        "dns": "192.168.111.1",
        "ntp_server": "",
        "omjs_properties": {"oms.use_linked_clone": "true",
                            "oms.skip_cluster_vmotion_check": "true",
                            "oms.disable_datastores_anti_affinity": "true"},
        "patches": ["vio-patch-201_2.0.1.3309787_all.deb"],
        "vc_host": "192.168.111.130",
        "vc_user": "Administrator@vsphere.local",
        "vc_password": "Admin!23",
        "datacenter": "vio-datacenter",
        "cluster": "mgmt_cluster",
        "datastore": "vdnetSharedStorage",
        "network": "VM Network",
        "openstack_creds_provider": "dynamic",
        "ext_net_cidr": "192.168.112.0/24",
        "ext_net_start_ip": "192.168.112.170",
        "ext_net_end_ip": "192.168.112.200",
        "ext_net_gateway": "192.168.112.1",
        "public_vip_pool": ["192.168.112.201", "192.168.112.202"],
        "private_vip_pool": ["192.168.111.201", "192.168.111.202"]
    }
    :param log_dir: directory deployment and test logs.
    :param cluster_spec: dict spec for creating OpenStack cluster from oms api.
    :param tests: string test name separated by comma.
    """
    LOG.debug('OMS spec: %s' % oms_spec)
    LOG.debug('Log path: %s' % log_dir)
    result = PASS
    vio_setup = VIO(oms_spec, cluster_spec, log_dir)
    vio_setup.deploy_vapp()
    if 'omjs_properties' in oms_spec:
        vio_setup.config_omjs(oms_spec['omjs_properties'])
    if 'version' not in oms_spec:
        oms_spec['version'] = vio_setup.get_version()
    if cluster_spec:
        LOG.debug('Cluster spec: %s' % cluster_spec)
        vio_setup.deploy_openstack()
    if 'patches' in oms_spec:
        ip_pool_idex = 0
        for patch in oms_spec['patches']:
            # Applying patches continuously is easy to fail. In real world,
            # user won't apply them like this. So sleep 3 minutes beforehand.
            LOG.debug('Sleep 3 minutes before patching.')
            time.sleep(60 * 3)
            vio_setup.apply_patch(patch)
            if 'vio-upgrade-' in patch:
                public_vip = oms_spec['public_vip_pool'][ip_pool_idex]
                private_vip = oms_spec['private_vip_pool'][ip_pool_idex]
                cluster_spec = vio_setup.upgrade(public_vip, private_vip)
    if tests:
        LOG.debug('Tests: %s' % tests)
        result = Test.run_tests(tests, log_dir, oms_spec, cluster_spec)
    vio_setup.get_support_bundle()
    return result
