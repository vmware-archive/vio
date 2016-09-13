import logging

from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneclient.v3 import client as keystone_client


LOG = logging.getLogger(__name__)
LOCAL_DOMAIN_ID = 'local'
DEFAULT_DOMAIN_ID = 'default'
ADMIN_PROJECT_NAME = 'admin'
ADMIN_ROLE_NAME = 'admin'


def create_if_not_exist(func, kind, name, **kwargs):
    entity = get_entity(func, kind, name)
    if entity:
        return entity
    LOG.info("Create %s %s" % (kind, name))
    return func.create(name, **kwargs)


def get_entity(func, kind, name, **kwargs):
    for entity in func.list(**kwargs):
        if entity.name.lower() == name.lower():
            LOG.info("Found %s %s" % (kind, name))
            return entity
    return None


def grant_role_on_project(keystone, project, user, role):
    for existed_role in keystone.roles.list(user=user, project=project):
        if existed_role.name == role.name:
            LOG.info('Role %s is already granted to user %s on project %s' %
                     (role.name, user.name, project.name))
        return
    LOG.info('Grant role %s to user %s on project %s', role.name, user.name,
             project.name)
    keystone.roles.grant(role, user=user, project=project)


def grant_role_on_domain(keystone, domain, user, role):
    for existed_role in keystone.roles.list(user=user, domain=domain):
        if existed_role.name == role.name:
            LOG.info('Role %s is already granted to user %s on domain %s' %
                     (role.name, user.name, domain.name))
            return
    LOG.info('Grant role %s to user %s on domain %s', role.name, user.name,
             domain.name)
    keystone.roles.grant(role, user=user, domain=domain)


def enable_ldap_admin(private_vip, local_user_name, local_user_pwd,
                      ldap_user_name):
    keystone = get_keystone_client(private_vip=private_vip,
                                   username=local_user_name,
                                   password=local_user_pwd,
                                   project_name=ADMIN_PROJECT_NAME,
                                   domain_name=LOCAL_DOMAIN_ID)
    ldap_domain = keystone.domains.get(DEFAULT_DOMAIN_ID)
    admin_role = get_entity(keystone.roles, 'role', ADMIN_ROLE_NAME)
    ldap_user = get_entity(keystone.users, 'user', ldap_user_name,
                           domain=DEFAULT_DOMAIN_ID)
    grant_role_on_domain(keystone,
                         domain=ldap_domain,
                         user=ldap_user,
                         role=admin_role)
    ldap_project = get_entity(keystone.projects, 'project',
                              ADMIN_PROJECT_NAME, domain=DEFAULT_DOMAIN_ID)
    if not ldap_project:
        LOG.info('Create project %s', ADMIN_PROJECT_NAME)
        keystone.projects.create(name=ADMIN_PROJECT_NAME,
                                 domain=DEFAULT_DOMAIN_ID)
    grant_role_on_project(keystone,
                          project=ldap_project,
                          user=ldap_user,
                          role=admin_role)


def get_keystone_client(private_vip, username, password, project_name,
                        domain_name):
    auth_url = get_auth_url(private_vip, 'v3', port='35357')
    auth = v3.Password(auth_url=auth_url,
                       username=username,
                       password=password,
                       project_name=project_name,
                       user_domain_name=domain_name,
                       project_domain_name=domain_name)
    sess = session.Session(auth=auth)
    return keystone_client.Client(session=sess)


def get_auth_url(private_vip, version='v2.0', port='5000'):
    return 'http://%s:%s/%s/' % (private_vip, port, version)
