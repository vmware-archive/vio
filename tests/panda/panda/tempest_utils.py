import logging
import os
import ConfigParser
import time

from novaclient import client as nova_client
from neutronclient.neutron import client as neutron_client
import yaml

from shellutil import shell
from exceptions import NotSupportedError
from cluster_utils import NSXT_BACKEND
from cluster_utils import NSXV_BACKEND
import task_utils
from os_utils import get_entity
from os_utils import get_keystone_client
from os_utils import create_if_not_exist
from os_utils import grant_role_on_project
from os_utils import get_auth_url
from os_utils import DEFAULT_DOMAIN_ID


LOG = logging.getLogger(__name__)
TEMPEST_DIR = 'tempest'
VMWARE_NSX_DIR = 'vmware-nsx'
VMWARE_TEMPEST_DIR = 'vmware_tempest'
PACKAGE_MAP = {'nova': 'tempest.api.compute',
               'cinder': 'tempest.api.volume',
               'neutron': 'tempest.api.network',
               'heat': 'tempest.api.orchestration',
               'keystone': 'tempest.api.identity',
               'glance': 'tempest.api.image',
               'scenario': 'tempest.scenario',
               'nsxv': 'vmware_nsx_tempest.tests.nsxv.',
               'nsxt': 'vmware_nsx_tempest.tests.nsxv3'}
LEGACY_PROVIDER = 'legacy'
DYNAMIC_PROVIDER = 'dynamic'
PRE_PROVISIONED_PROVIDER = 'pre-provisioned'
ROLE_NAME = 'member-tempest'
STORAGE_ROLE_NAME = 'storage-ops-tempest'
IMAGE_NAME = 'ubuntu-14.04-server-amd64'
FLAVOR1_NAME = 'm1-tempest'
FLAVOR2_NAME = 'm2-tempest'
DATA_NET_NAME = 'flat-tempest'
DATA_NET_CIDR = '172.16.10.0/24'
EXT_NET_NAME = 'public-tempest'
ROUTER_NAME = 'router-tempest'
TENANT_NAME = 'default-tenant-tempest'
ALT_TENANT_NAME = 'alt-tenant-tempest'
GIT_CLONE = 'GIT_SSL_NO_VERIFY=true git clone'


def get_data_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


def install_tempest(repository='github.com/openstack/tempest.git',
                    branch='11.0.0',
                    nsx_repo='github.com/openstack/vmware-nsx',
                    nsx_branch='stable/mitaka',
                    protocol='http',
                    conf_template=None):
    if os.path.exists(TEMPEST_DIR):
        LOG.info('Tempest already exists, skip cloning.')
    else:
        LOG.info('Clone tempest from repository.')
        clone_url = '%s://%s' % (protocol, repository)
        shell.local('%s -b %s %s' % (GIT_CLONE, branch, clone_url),
                    raise_error=True)
    # Get vmware_nsx plugin
    if os.path.exists(VMWARE_NSX_DIR):
        LOG.info('vmware-nsx already exists, skip cloning.')
    else:
        LOG.info('Clone vmware-nsx from repository.')
        clone_url = '%s://%s' % (protocol, nsx_repo)
        shell.local('%s -b %s %s' % (GIT_CLONE, nsx_branch, clone_url),
                    raise_error=True)
    with shell.cd(TEMPEST_DIR):
        shell.local("sed -i 's/-500/-1500/g' .testr.conf")
        LOG.info('Copy template to etc/tempest.conf')
        conf_template = conf_template or os.path.join(get_data_path(),
                                                      'tempest.conf.template')
        shell.local('cp %s etc/tempest.conf' % conf_template, raise_error=True)
        LOG.info('Install tempest dependencies.')
        cmd = 'python tools/install_venv.py --no-site-packages'
        task_utils.safe_run(cmd, 'install tempest dependency')
    LOG.info('Install vmware-nsx.')
    cmd = './%s/tools/with_venv.sh pip install -e %s' % (TEMPEST_DIR,
                                                         VMWARE_NSX_DIR)
    task_utils.safe_run(cmd, 'install vmware-nsx')
    LOG.info('Tempest has been successfully installed.')


def add_account(user_name, password, tenant_name, roles=None, network=None,
                router=None):
    account = {
        'username': user_name,
        'password': password,
        'tenant_name': tenant_name
    }
    if roles:
        account['roles'] = roles
    if network or router:
        account['resources'] = []
        if network:
            account['resources'].append(network)
        if router:
            account['resources'].append(router)
    return account


def config_identity(config_parser, private_vip, admin_user_name, admin_pwd,
                    admin_tenant_name, creds_provider, default_user_name=None,
                    default_pwd=None, alt_user_name=None, alt_pwd=None):
    uri_v3 = get_auth_url(private_vip, 'v3')
    uri_v2 = get_auth_url(private_vip)
    keystone = get_keystone_client(private_vip=private_vip,
                                   username=admin_user_name,
                                   password=admin_pwd,
                                   project_name=admin_tenant_name,
                                   domain_name=DEFAULT_DOMAIN_ID)
    admin_tenant = get_entity(keystone.projects, 'project', admin_tenant_name)
    config_parser.set('identity', 'uri_v3', uri_v3)
    config_parser.set('identity', 'uri', uri_v2)
    config_parser.set('identity', 'auth_version', 'v2')
    config_parser.set('auth', 'admin_tenant_name', admin_tenant_name)
    config_parser.set('auth', 'admin_password', admin_pwd)
    config_parser.set('auth', 'admin_username', admin_user_name)
    # Create tempest test role
    test_role = create_if_not_exist(keystone.roles, 'role', ROLE_NAME)
    config_parser.set('auth', 'tempest_roles', ROLE_NAME)
    # Both SQL backend and LDAP backend is Default
    config_parser.set('auth', 'admin_domain_name', 'Default')
    if creds_provider in [LEGACY_PROVIDER, PRE_PROVISIONED_PROVIDER]:
        # Create default tenant and user
        default_domain = keystone.domains.get(DEFAULT_DOMAIN_ID)
        default_tenant = create_if_not_exist(keystone.projects, 'project',
                                             TENANT_NAME,
                                             domain=default_domain)
        default_user = create_if_not_exist(keystone.users, 'user',
                                           default_user_name,
                                           password=default_pwd,
                                           tenant_id=default_tenant.id)

        grant_role_on_project(keystone, default_tenant, default_user,
                              test_role)
        # Create alter tenant and user
        alt_tenant = create_if_not_exist(keystone.projects, 'project',
                                         ALT_TENANT_NAME,
                                         domain=default_domain)
        alt_user = create_if_not_exist(keystone.users, 'user', alt_user_name,
                                       password=alt_pwd,
                                       tenant_id=alt_tenant.id)

        grant_role_on_project(keystone, alt_tenant, alt_user, test_role)
        if LEGACY_PROVIDER == creds_provider:
            # Legacy provider can only be used before Newton release.
            config_parser.set('identity', 'tenant_name', TENANT_NAME)
            config_parser.set('identity', 'username', default_user_name)
            config_parser.set('identity', 'password', default_pwd)
            config_parser.set('identity', 'alt_tenant_name', ALT_TENANT_NAME)
            config_parser.set('identity', 'alt_username', alt_user_name)
            config_parser.set('identity', 'alt_password', alt_pwd)
        elif PRE_PROVISIONED_PROVIDER == creds_provider:
            accounts = list()
            accounts.append(add_account(default_user_name, default_pwd,
                                        TENANT_NAME, roles=[ROLE_NAME]))
            accounts.append(add_account(alt_user_name, alt_pwd,
                                        ALT_TENANT_NAME, roles=[ROLE_NAME]))
            accounts.append(add_account(admin_user_name, admin_pwd,
                                        admin_tenant_name, roles=['admin']))
            test_accounts_file = os.path.join(os.getcwd(), TEMPEST_DIR,
                                              'etc/accounts.yaml')
            with open(test_accounts_file, 'w') as fh:
                yaml.dump(accounts, fh, default_flow_style=False,
                          default_style=False, indent=2, encoding='utf-8',
                          allow_unicode=True)
            config_parser.set('auth', 'test_accounts_file', test_accounts_file)
        config_parser.set('auth', 'use_dynamic_credentials', 'false')
        config_parser.set('auth', 'create_isolated_networks', 'false')
    elif creds_provider == DYNAMIC_PROVIDER:
        config_parser.set('auth', 'use_dynamic_credentials', 'true')
        config_parser.set('auth', 'create_isolated_networks', 'false')
    else:
        raise NotSupportedError('Not support %s' % creds_provider)
    # Create role for object storage
    create_if_not_exist(keystone.roles, 'role', STORAGE_ROLE_NAME)
    config_parser.set('object-storage', 'operator_role', STORAGE_ROLE_NAME)
    # Create role and add it to admin user for heat tempest tests.
    heat_role = get_entity(keystone.roles, 'role', 'heat_stack_owner')
    if not heat_role:
        LOG.info("Create role heat_stack_owner")
        heat_role = keystone.roles.create('heat_stack_owner')
        admin_user = get_entity(keystone.users, 'user', admin_user_name)
        grant_role_on_project(keystone, admin_tenant, admin_user, heat_role)


def config_compute(config_parser, private_vip, user_name, password,
                   tenant_name, endpoint_type='internalURL',
                   min_compute_nodes=1):
    auth_url = get_auth_url(private_vip)
    nova = nova_client.Client('2', user_name, password, tenant_name, auth_url,
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
    config_parser.set('orchestration', 'instance_type', FLAVOR1_NAME)
    m2 = create_if_not_exist(nova.flavors, 'flavor', FLAVOR2_NAME, ram=1024,
                             vcpus=2, disk=10, is_public=True)
    config_parser.set('compute', 'flavor_ref_alt', m2.id)
    config_parser.set('compute', 'min_compute_nodes', min_compute_nodes)
    config_parser.set('compute-feature-enabled', 'pause', 'false')


def get_network(neutron, net_name):
    nets = neutron.list_networks()['networks']
    for net in nets:
        if net['name'] == net_name:
            return net


def config_network(config_parser, private_vip, user_name, password,
                   neutron_backend, tenant_name, ext_net_cidr=None,
                   ext_net_start_ip=None, ext_net_end_ip=None,
                   ext_net_gateway=None, endpoint_type='internalURL'):
    auth_url = get_auth_url(private_vip)
    neutron = neutron_client.Client('2.0', username=user_name,
                                    password=password,
                                    tenant_name=tenant_name,
                                    auth_url=auth_url,
                                    insecure=True,
                                    endpoint_type=endpoint_type)
    data_network = get_network(neutron, DATA_NET_NAME)
    if not data_network:
        # Create fixed network
        if NSXV_BACKEND == neutron_backend:
            net_spec = {
                "network":
                    {
                        "name": DATA_NET_NAME,
                        "admin_state_up": True,
                        "shared": True
                    }
            }
        else:
            net_spec = {
                "network":
                    {
                        "provider:network_type": "flat",
                        "name": DATA_NET_NAME,
                        "provider:physical_network": "dvs",
                        "admin_state_up": True,
                        "shared": True
                    }
            }
        LOG.info("Create data network %s.", DATA_NET_NAME)
        data_network = neutron.create_network(net_spec)['network']
        # Create data subnet
        # TODO: Create a static subnet as fixed network while using dynamic
        # credentials.
        subnet_spec = {
            'subnet':
                {
                    "name": DATA_NET_NAME,
                    'network_id': data_network['id'],
                    'cidr': DATA_NET_CIDR,
                    'ip_version': 4,
                    'enable_dhcp': True
                }
        }
        LOG.info("Create %s subnet.", DATA_NET_NAME)
        data_subnet = neutron.create_subnet(subnet_spec)['subnet']
        data_network['subnets'] = [data_subnet['id']]
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
                        "name": EXT_NET_NAME,
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
            LOG.info("Create router %s.", ROUTER_NAME)
            router_spec = {
                'router':
                    {
                        'name': ROUTER_NAME,
                        'external_gateway_info':
                            {
                                'network_id': ext_network['id']
                            }
                    }
            }
            router = neutron.create_router(router_spec)['router']
            LOG.info("Add %s to router %s", DATA_NET_NAME, ROUTER_NAME)
            add_router_interface_spec = {
                'subnet_id': data_network['subnets'][0]
            }
            neutron.add_interface_router(router['id'],
                                         add_router_interface_spec)
        else:
            LOG.info("Found external network %s", EXT_NET_NAME)
        config_parser.set('network', 'public_network_id', ext_network['id'])
        config_parser.set('network-feature-enabled', 'api_extensions',
                          'binding, dist-router, multi-provider, provider, '
                          'quotas,external-net, extraroute, router, '
                          'security-group')
        config_parser.set('network-feature-enabled',
                          'port_admin_state_change', 'False')
        config_parser.set('network-feature-enabled', 'ipv6', 'False')
        config_parser.set('validation', 'connect_method', 'floating')
        config_parser.set('network', 'floating_network_name', EXT_NET_NAME)
        config_parser.set('validation', 'run_validation', 'true')
    else:
        config_parser.set('network', 'tenant_network_cidr', DATA_NET_CIDR)
        config_parser.set('network', 'tenant_network_mask_bits', '24')
        config_parser.set('validation', 'run_validation', 'false')


def config_volume(config_parser, private_vip, user_name, password, tenant_name,
                  endpoint_type='internalURL'):
    auth_url = get_auth_url(private_vip)
    nova = nova_client.Client('2', user_name, password, tenant_name, auth_url,
                              insecure=True, endpoint_type=endpoint_type)
    # Get Nova API versions
    versions = nova.versions.list()
    if (len(versions) == 1 and
            versions[0].to_dict().get('status') == 'SUPPORTED'):
        config_parser.set('volume', 'storage_protocol', 'LSI Logic SCSI')


def config_nsx(config_parser, nsx_manager, nsx_user, nsx_pwd):
    if not config_parser.has_section('nsxv'):
        config_parser.add_section('nsxv')
    config_parser.set('nsxv', 'manager_uri', 'http://%s' % nsx_manager)
    config_parser.set('nsxv', 'user', nsx_user)
    config_parser.set('nsxv', 'password', nsx_pwd)


def config_tempest(private_vip, admin_user, admin_pwd, neutron_backend,
                   creds_provider, default_user=None, default_pwd=None,
                   alter_user=None, alter_pwd=None, ext_net_cidr=None,
                   ext_net_start_ip=None, ext_net_end_ip=None,
                   ext_net_gateway=None, tempest_log_file=None,
                   admin_tenant='admin', min_compute_nodes=1, nsx_manager=None,
                   nsx_user=None, nsx_pwd=None):
    config_parser = ConfigParser.ConfigParser()
    conf_path = '%s/etc/tempest.conf' % TEMPEST_DIR
    config_parser.read(conf_path)
    config_identity(config_parser, private_vip, admin_user, admin_pwd,
                    admin_tenant, creds_provider, default_user, default_pwd,
                    alter_user, alter_pwd)
    config_compute(config_parser, private_vip, admin_user, admin_pwd,
                   admin_tenant, min_compute_nodes=min_compute_nodes)
    config_network(config_parser, private_vip, admin_user, admin_pwd,
                   neutron_backend, admin_tenant, ext_net_cidr,
                   ext_net_start_ip, ext_net_end_ip, ext_net_gateway)
    if neutron_backend in [NSXT_BACKEND, NSXV_BACKEND]:
        config_nsx(config_parser, nsx_manager, nsx_user, nsx_pwd)
    config_volume(config_parser, private_vip, admin_user, admin_pwd,
                  admin_tenant)
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
    all_tests = dict([split_name_and_id(line) for line in lines.split('\n')
                     if line.startswith('tempest.') or
                     line.startswith('vmware_nsx_tempest.')])

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


def make_reports(report_dir, suite_name):
    subunit = '/tmp/%s-subunit.txt' % suite_name
    junit_xml = os.path.join(report_dir, '%s_results.xml' % suite_name)
    shell.local('./tools/with_venv.sh testr last --subunit > %s' % subunit)
    shell.local('subunit2junitxml --output-to=%s < %s' % (junit_xml, subunit))
    html_report_file = os.path.join(report_dir, '%s_results.html' % suite_name)
    try:
        shell.local('subunit2html %s %s' % (subunit, html_report_file),
                    raise_error=True)
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
        start = time.time()
        shell.local("./tools/with_venv.sh testr run %s --subunit --load-list="
                    "%s.txt | subunit2pyunit" % (testr_opts, component))
        end = time.time()
        LOG.info('%s tests took %s seconds', component, (end - start))
        make_reports(report_dir, component)
        failed_tests = shell.local('./tools/with_venv.sh testr failing '
                                   '--subunit | subunit-ls')[1]
        if failed_tests.strip():
            LOG.info('Failed tests:\n%s', failed_tests)
            if rerun_failed:
                LOG.info('Rerun above failed tests.')
                start = time.time()
                shell.local('./tools/with_venv.sh testr run --failing '
                            '--subunit | subunit2pyunit')
                end = time.time()
                LOG.info('Rerun %s failed tests took %s seconds', component,
                         (end - start))
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
    # Delete below to use Mitaka tempest after Xiangfei remove dependency to
    # p3 tempest
    if os.path.exists('p3-tempest'):
        LOG.info('P3 tempest already exists, skip cloning.')
    else:
        LOG.info('Clone P3 tempest from repository.')
        shell.local('git clone http://p3-review.eng.vmware.com/tempest '
                    'p3-tempest', raise_error=True)
        # copy tempest.conf
        shell.local('cp -f %s/etc/tempest.conf %s/etc/' %
                    (TEMPEST_DIR, 'p3-tempest'))
        # put config in [auth] to [identity]
        config_parser = ConfigParser.ConfigParser()
        conf_path = '%s/etc/tempest.conf' % 'p3-tempest'
        config_parser.read(conf_path)
        auth_configs = config_parser.items('auth')
        for auth_config in auth_configs:
            config_parser.set('identity', auth_config[0], auth_config[1])
        config_parser.write(open(conf_path, 'w'))
    if not os.path.exists(os.path.join(VMWARE_TEMPEST_DIR, '.venv')):
        LOG.info('Create virtual env for VMware tempest.')
        shell.local('virtualenv %s/.venv' % VMWARE_TEMPEST_DIR)
    tempest_path = os.path.join(os.getcwd(), 'p3-tempest')
    install_cmd = '''set -ex
    cd {path}
    source .venv/bin/activate
    pip --no-cache-dir install -e {tempest_path}
    pip --no-cache-dir install nose
    pip --no-cache-dir install nose-testconfig
    pip --no-cache-dir install pyvmomi
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
