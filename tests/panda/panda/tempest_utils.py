import logging
import os
import time
import ConfigParser
from urlparse import urlparse

from keystoneclient.v2_0 import client as keystone_client
from novaclient.v2 import client as nova_client
from neutronclient.v2_0 import client as neutron_client

from shellutil import shell
from exceptions import NotSupportedError
from subunit2html import generate_html_report
from cluster_utils import NSXV_BACKEND
from cluster_utils import DVS_BACKEND


LOG = logging.getLogger(__name__)
TEMPEST_DIR = 'tempest'
VMWARE_TEMPEST_DIR = 'vmware_tempest'
PACKAGE_MAP = {'nova': 'tempest.api.compute',
               'cinder': 'tempest.api.volume',
               'neutron': 'tempest.api.network',
               'heat': 'tempest.api.orchestration',
               'keystone': 'tempest.api.identity',
               'glance': 'tempest.api.image',
               'scenario': 'tempest.scenario'}
LEGACY_PROVIDER = 'legacy'
DYNAMIC_PROVIDER = 'dynamic'
PRE_PROVISIONED_PROVIDER = 'pre-provisioned'
ROLE_NAME = 'member-tempest'
STORAGE_ROLE_NAME = 'storage-ops-tempest'
IMAGE_NAME = 'ubuntu-14.04-server-amd64'
FLAVOR1_NAME = 'm1-tempest'
FLAVOR2_NAME = 'm2-tempest'
DATA_NET_NAME = 'flat-tempest'
EXT_NET_NAME = 'public-tempest'
TENANT_NAME = 'default-tenant-tempest'
ALT_TENANT_NAME = 'alt-tenant-tempest'


def get_data_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


def install_tempest(repository='http://p3-review.eng.vmware.com/tempest',
                    branch='master',
                    conf_template=None):
    if os.path.exists(TEMPEST_DIR):
        LOG.info('Tempest already exists, skip cloning.')
    else:
        LOG.info('Clone tempest from repository.')
        shell.local('git clone -b %s %s' % (branch, repository),
                    raise_error=True)
    with shell.cd(TEMPEST_DIR):
        shell.local("sed -i 's/-500/-1500/g' .testr.conf")
        LOG.info('Copy template to etc/tempest.conf')
        conf_template = conf_template or os.path.join(get_data_path(),
                                                      'tempest.conf.template')
        shell.local('cp %s etc/tempest.conf' % conf_template, raise_error=True)
        LOG.info('Install tempest dependencies.')
        cmd = 'python tools/install_venv.py --no-site-packages'
        exit_code = shell.local(cmd)[0]
        if exit_code:
            LOG.warning('Failed to install dependencies. Retry it after 3 '
                        'minutes.')
            time.sleep(60 * 3)
            shell.local(cmd, raise_error=True)
    LOG.info('Tempest has been successfully installed.')


def create_if_not_exist(func, kind, name, **kwargs):
    entity = get_entity(func, kind, name)
    if entity:
        return entity
    LOG.info("Create %s %s" % (kind, name))
    return func.create(name, **kwargs)


def get_entity(func, kind, name):
    for entity in func.list():
        if entity.name.lower() == name.lower():
            LOG.info("Found %s %s" % (kind, name))
            return entity
    return None


def add_user_to_tenant(keystone, tenant, user, role):
    users = tenant.list_users()
    for existed_user in users:
        if existed_user.name == user.name:
            return
    LOG.info('Grant role %s to user %s in tenant %s' %
             (role.name, user.name, tenant.name))
    keystone.roles.add_user_role(user, role, tenant=tenant)


def config_identity(config_parser, auth_url, admin_user_name, admin_pwd,
                    admin_tenant_name, creds_provider, default_user_name=None,
                    default_pwd=None, alt_user_name=None, alt_pwd=None):
    uri_v3 = 'http://%s/v3/' % urlparse(auth_url).netloc
    keystone = keystone_client.Client(username=admin_user_name,
                                      password=admin_pwd,
                                      tenant_name=admin_tenant_name,
                                      auth_url=auth_url,
                                      insecure=True)
    admin_tenant = get_entity(keystone.tenants, 'tenant', admin_tenant_name)
    config_parser.set('identity', 'admin_tenant_id', admin_tenant.id)
    config_parser.set('identity', 'admin_tenant_name', admin_tenant_name)
    config_parser.set('identity', 'admin_password', admin_pwd)
    config_parser.set('identity', 'admin_username', admin_user_name)
    config_parser.set('identity', 'uri_v3', uri_v3)
    config_parser.set('identity', 'uri', auth_url)
    # Create member role
    create_if_not_exist(keystone.roles, 'role', ROLE_NAME)
    config_parser.set('auth', 'tempest_roles', ROLE_NAME)
    if LEGACY_PROVIDER == creds_provider:
        # Create default tenant and user
        default_tenant = create_if_not_exist(keystone.tenants, 'tenant',
                                             TENANT_NAME)
        default_user = create_if_not_exist(keystone.users, 'user',
                                           default_user_name,
                                           password=default_pwd,
                                           tenant_id=default_tenant.id)
        config_parser.set('identity', 'tenant_name', TENANT_NAME)
        config_parser.set('identity', 'username', default_user_name)
        config_parser.set('identity', 'password', default_pwd)
        admin_role = get_entity(keystone.roles, 'role', 'admin')
        add_user_to_tenant(keystone, default_tenant, default_user,
                           admin_role)
        # Create alter tenant and user
        alt_tenant = create_if_not_exist(keystone.tenants, 'tenant',
                                         ALT_TENANT_NAME)
        alt_user = create_if_not_exist(keystone.users, 'user', alt_user_name,
                                       password=alt_pwd,
                                       tenant_id=alt_tenant.id)
        config_parser.set('identity', 'alt_tenant_name', ALT_TENANT_NAME)
        config_parser.set('identity', 'alt_username', alt_user_name)
        config_parser.set('identity', 'alt_password', alt_pwd)
        add_user_to_tenant(keystone, alt_tenant, alt_user, admin_role)
        config_parser.set('auth', 'allow_tenant_isolation', 'false')
    else:
        config_parser.set('auth', 'allow_tenant_isolation', 'true')
    # Create role for object storage
    create_if_not_exist(keystone.roles, 'role', STORAGE_ROLE_NAME)
    config_parser.set('object-storage', 'operator_role', STORAGE_ROLE_NAME)
    # Create role and add it to admin user for heat tempest tests.
    heat_role = get_entity(keystone.roles, 'role', 'heat_stack_owner')
    if not heat_role:
        LOG.info("Create role heat_stack_owner")
        heat_role = keystone.roles.create('heat_stack_owner')
        admin_user = get_entity(keystone.users, 'user', admin_user_name)
        add_user_to_tenant(keystone, admin_tenant, admin_user, heat_role)


def config_compute(config_parser, auth_url, user_name, password,
                   tenant_name, endpoint_type='internalURL'):
    nova = nova_client.Client(username=user_name, api_key=password,
                              project_id=tenant_name, auth_url=auth_url,
                              insecure=True, endpoint_type=endpoint_type)
    # Get the default image.
    images = nova.images.list()
    if len(images) == 0:
        raise NotSupportedError('At least 1 image in glance is required.')
    default_image = images[0]
    for image in images:
        if image.name == IMAGE_NAME:
            default_image = image
            images.remove(image)
    LOG.info('Use image %s as default image in tempest', default_image.name)
    alt_image = images[0] if len(images) > 0 else default_image
    LOG.info('Use image %s as alter image in tempest', alt_image.name)
    config_parser.set('compute', 'image_ref', default_image.id)
    config_parser.set('compute', 'image_ref_alt', alt_image.id)
    # Create the flavors
    m1 = create_if_not_exist(nova.flavors, 'flavor', FLAVOR1_NAME, ram=512,
                             vcpus=1, disk=10, is_public=True)
    config_parser.set('compute', 'flavor_ref', m1.id)
    m2 = create_if_not_exist(nova.flavors, 'flavor', FLAVOR2_NAME, ram=1024,
                             vcpus=2, disk=10, is_public=True)
    config_parser.set('compute', 'flavor_ref_alt', m2.id)
    config_parser.set('compute-feature-enabled', 'pause', 'false')


def get_network(neutron, net_name):
    nets = neutron.list_networks()['networks']
    for net in nets:
        if net['name'] == net_name:
            return net


def config_network(config_parser, auth_url, user_name, password,
                   neutron_backend, tenant_name, ext_net_cidr=None,
                   ext_net_start_ip=None, ext_net_end_ip=None,
                   ext_net_gateway=None, endpoint_type='internalURL'):
    neutron = neutron_client.Client(username=user_name, password=password,
                                    tenant_name=tenant_name, auth_url=auth_url,
                                    insecure=True, endpoint_type=endpoint_type)
    data_network = get_network(neutron, DATA_NET_NAME)
    if not data_network:
        # Create data network
        if NSXV_BACKEND == neutron_backend:
            net_spec = {
                "network":
                    {
                        "name": DATA_NET_NAME,
                        "admin_state_up": True
                    }
            }
        else:
            net_spec = {
                "network":
                    {
                        "provider:network_type": "flat",
                        "name": DATA_NET_NAME,
                        "provider:physical_network": "dvs",
                        "admin_state_up": True
                    }
            }
        LOG.info("Create data network %s.", DATA_NET_NAME)
        data_network = neutron.create_network(net_spec)['network']
        # Create data subnet
        subnet_spec = {
            'subnet':
                {
                    'network_id': data_network['id'],
                    'cidr': '172.16.10.0/24',
                    'ip_version': 4,
                    'enable_dhcp': True
                }
        }
        LOG.info("Create %s subnet.", DATA_NET_NAME)
        neutron.create_subnet(subnet_spec)
    else:
        LOG.info("Found data network %s", DATA_NET_NAME)
    config_parser.set('compute', 'fixed_network_name', DATA_NET_NAME)
    if NSXV_BACKEND == neutron_backend:
        ext_network = get_network(neutron, EXT_NET_NAME)
        if not ext_network:
            # Create external network
            net_spec = {
                "network":
                    {
                        "router:external": "True",
                        "name": EXT_NET_NAME,
                        "admin_state_up": True
                    }
            }
            LOG.info("Create external network %s.", EXT_NET_NAME)
            ext_network = neutron.create_network(net_spec)['network']
            # Create external subnet
            subnet_spec = {
                'subnet':
                    {
                        'network_id': ext_network['id'],
                        'cidr': ext_net_cidr,
                        'ip_version': 4,
                        'enable_dhcp': False,
                        'gateway_ip': ext_net_gateway,
                        'allocation_pools': [{"start": ext_net_start_ip,
                                              "end": ext_net_end_ip}]
                    }
            }
            LOG.info("Create %s subnet.", EXT_NET_NAME)
            neutron.create_subnet(subnet_spec)
        else:
            LOG.info("Found external network %s", EXT_NET_NAME)
        config_parser.set('network', 'public_network_id', ext_network['id'])
        config_parser.set('network-feature-enabled', 'api_extensions',
                          'binding, dist-router, multi-provider, provider, '
                          'quotas,external-net, extraroute, router, '
                          'security-group')
        config_parser.set('network-feature-enabled', 'ipv6', 'false')
        config_parser.set('network', 'public_network_id', ext_network['id'])


def config_tempest(private_vip, admin_user, admin_pwd, neutron_backend,
                   creds_provider, default_user=None, default_pwd=None,
                   alter_user=None, alter_pwd=None, ext_net_cidr=None,
                   ext_net_start_ip=None, ext_net_end_ip=None,
                   ext_net_gateway=None, tempest_log_file=None,
                   admin_tenant='admin'):
    config_parser = ConfigParser.ConfigParser()
    conf_path = '%s/etc/tempest.conf' % TEMPEST_DIR
    config_parser.read(conf_path)
    auth_url = "http://%s:5000/v2.0/" % private_vip
    config_identity(config_parser, auth_url, admin_user, admin_pwd,
                    admin_tenant, creds_provider, default_user, default_pwd,
                    alter_user, alter_pwd)
    config_compute(config_parser, auth_url, admin_user, admin_pwd,
                   admin_tenant)
    config_network(config_parser, auth_url, admin_user, admin_pwd,
                   neutron_backend, admin_tenant, ext_net_cidr,
                   ext_net_start_ip, ext_net_end_ip, ext_net_gateway)
    if tempest_log_file:
        config_parser.set('DEFAULT', 'log_file', tempest_log_file)
    # Configure darshboard
    config_parser.set('dashboard', 'login_url',
                      'http://%s/auth/login' % private_vip)
    config_parser.set('dashboard', 'dashboard_url', 'http://%s/' % private_vip)
    LOG.info('Update configurations to %s' % conf_path)
    config_parser.write(open(conf_path, 'w'))


def split_name_and_id(line):
    index = line.find('[')
    if index > 0:
        return line[0:index], line[index:]
    else:
        return line, ''


def strip_id(line):
    line = line.replace('\n', '').strip()
    index = line.find('[')
    if index > 0:
        return line[0:index]
    else:
        return line


def write_suite_file(name, test_list):
    LOG.info('Write test suite %s.txt' % name)
    with open('%s/%s.txt' % (TEMPEST_DIR, name), 'w') as f:
        for test in test_list:
            f.write(test)
            f.write('\n')


def generate_run_list(neutron_backend):
    with shell.cd(TEMPEST_DIR):
        if not os.path.exists('%s/.testrepository' % TEMPEST_DIR):
            shell.local('./tools/with_venv.sh testr init', raise_error=True)
        lines = shell.local('./tools/with_venv.sh testr list-tests',
                            raise_error=True)[1]
    # Obtain all tests into a dict {test_name: test_id}
    all_tests = dict([split_name_and_id(line)
                     for line in lines.split('\n')
                     if line.startswith('tempest.')])

    # Get excluded tests into a list [test_name]
    exclude_file = '%s/%s-excluded-tests.txt' % (get_data_path(),
                                                 neutron_backend)
    if os.path.exists(exclude_file):
        LOG.debug('Found %s, tests in it will be excluded.', exclude_file)
        excluded_tests = [strip_id(line) for line in open(exclude_file)
                          if (line.strip() != '') and
                          (not line.strip().startswith('#'))]
    else:
        excluded_tests = []
        LOG.debug('Excluded list not found, all tests will be included')
    # Get all tests minus excluded tests [test_name + test_id]
    exec_tests = [test_name + test_id for (test_name, test_id)
                  in all_tests.items() if test_name not in excluded_tests]

    # Get test case and exclude metrics
    num_all_tests = len(all_tests)
    num_excluded = len(excluded_tests)
    num_tests = len(exec_tests)

    LOG.debug('Total number of available tests: %s' % num_all_tests)
    LOG.debug('Total number of excluded tests: %s' % num_excluded)
    LOG.debug('Total number of tests to run: %s' % num_tests)

    outdated_tests = []
    if num_tests != num_all_tests - num_excluded:
        all_tests_list = all_tests.keys()
        outdated_tests = [test_name for test_name in excluded_tests
                          if test_name not in all_tests_list]
    if outdated_tests:
        LOG.debug('Below tests in exclude-tests.txt are outdated.')
        for test in outdated_tests:
            LOG.debug(test)

    write_suite_file('included-tests', exec_tests)
    test_list = [test_name + test_id for (test_name, test_id)
                 in all_tests.items()]
    write_suite_file('all-tests', test_list)
    for key in PACKAGE_MAP:
        test_list = [test for test in exec_tests
                     if test.startswith(PACKAGE_MAP[key])]
        write_suite_file(key, test_list)
    # Use neutron include list when it is dvs
    if neutron_backend == DVS_BACKEND:
        shell.local('cp -f %s/dvs-included-neutron.txt %s/neutron.txt' %
                    (get_data_path(), TEMPEST_DIR))


def make_reports(report_dir, suite_name):
    subunit = '/tmp/%s-subunit.txt' % suite_name
    junit_xml = os.path.join(report_dir, '%s_results.xml' % suite_name)
    shell.local('./tools/with_venv.sh testr last --subunit > %s' % subunit)
    shell.local('subunit2junitxml --output-to=%s < %s' % (junit_xml, subunit))
    html_report_file = os.path.join(report_dir, '%s_results.html' % suite_name)
    try:
        generate_html_report(subunit, html_report_file)
        LOG.info('Generated report to %s.' % html_report_file)
    except Exception:
        LOG.exception('Failed to generate report to %s.' % html_report_file)


def run_test(component, report_dir, parallel=False, rerun_failed=False):
    testr_opts = ''
    if parallel:
        testr_opts += '--parallel'
    if not os.path.isabs(report_dir):
        report_dir = os.path.abspath(report_dir)
    with shell.cd(TEMPEST_DIR):
        LOG.info('Start to run %s tests' % component)
        shell.local("./tools/with_venv.sh testr run %s --subunit --load-list="
                    "%s.txt | subunit2pyunit" % (testr_opts, component))
        make_reports(report_dir, component)
        failed_tests = shell.local('./tools/with_venv.sh testr failing '
                                   '--subunit | subunit-ls')[1]
        if failed_tests.strip():
            LOG.info('Failed tests:\n%s', failed_tests)
            if rerun_failed:
                LOG.info('Rerun above failed tests.')
                shell.local('./tools/with_venv.sh testr run --failing '
                            '--subunit | subunit2pyunit')
                make_reports(report_dir, '%s_rerun' % component)


def install_vmware_tempest(
        repository='http://p3-review.eng.vmware.com/vmware_tempest',
        branch='master'):
    if os.path.exists(VMWARE_TEMPEST_DIR):
        LOG.info('VMware tempest already exists, skip cloning.')
    else:
        LOG.info('Clone VMware tempest from repository.')
        shell.local('git clone -b %s %s' % (branch, repository),
                    raise_error=True)
    if not os.path.exists(os.path.join(VMWARE_TEMPEST_DIR, '.venv')):
        LOG.info('Copy virtual env packages from tempest to VMware tempest.')
        shell.local('cp -rf %s/.venv %s/' % (TEMPEST_DIR, VMWARE_TEMPEST_DIR))
    tempest_path = os.path.join(os.getcwd(), TEMPEST_DIR)
    install_cmd = '''set -ex
    cd {path}
    source .venv/bin/activate
    pip install -r requirements.txt
    pip install -r test-requirements.txt
    pip install -e {tempest_path}
    cp -f vmware_tempest.cfg.sample vmware_tempest.cfg
    '''.format(path=VMWARE_TEMPEST_DIR, tempest_path=tempest_path)
    LOG.info('Install VMware tempest dependencies.')
    shell.local(install_cmd, raise_error=True)
    LOG.info('VMware tempest has been successfully installed.')


def config_vmware_tempest(vc_host, vc_user, vc_password):
    config_parser = ConfigParser.ConfigParser()
    conf_path = os.path.join(VMWARE_TEMPEST_DIR, 'vmware_tempest.cfg')
    config_parser.read(conf_path)
    config_parser.set('DEFAULT', 'RELEASE', 'VIO')
    config_parser.set('DEFAULT', 'VMWAREAPI_IP', vc_host)
    config_parser.set('DEFAULT', 'VMWAREAPI_USER', vc_user)
    config_parser.set('DEFAULT', 'VMWAREAPI_PASSWORD', vc_password)
    # TODO: Storage profile configuration
    LOG.info('Update configurations to %s' % conf_path)
    config_parser.write(open(conf_path, 'w'))


def generate_vmware_run_list():
    run_list_file = 'run-tests.txt'
    excluded_file = os.path.join(get_data_path(), 'vmware-excluded-tests.txt')
    cmd = '''set -ex
    cd {path}
    source .venv/bin/activate
    if [ ! -d '.testrepository' ]; then testr init; fi
    testr list-tests | grep '^vmware_tempest' | sort > all-tests.txt
    grep '^vmware_tempest' {excluded_file} | sort > excluded-tests.txt
    comm -23 all-tests.txt excluded-tests.txt > {run_list_file}
    '''.format(path=VMWARE_TEMPEST_DIR, excluded_file=excluded_file,
               run_list_file=run_list_file)
    LOG.info('Write test list to %s.', run_list_file)
    shell.local(cmd, raise_error=True)


def run_vmware_test(report_dir):
    if not os.path.isabs(report_dir):
        report_dir = os.path.abspath(report_dir)
    LOG.info('Start to run VMware tempest.')
    with shell.cd(VMWARE_TEMPEST_DIR):
        shell.local('source .venv/bin/activate && testr run --subunit '
                    '--load-list run-tests.txt | subunit2pyunit')
        failed_tests = shell.local('./tools/with_venv.sh testr failing '
                                   '--subunit | subunit-ls')[1]
        make_reports(report_dir, 'vmware')
        if failed_tests.strip():
            LOG.info('Failed tests:\n%s', failed_tests)
            # Maybe rerun failed tests
