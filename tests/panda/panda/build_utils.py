import os
import logging

from buildwebapi import api as buildapi
from task_utils import safe_run


LOG = logging.getLogger(__name__)


def get_build_type(build_id):
    build = get_build(build_id)
    LOG.debug('%s is %s build', build_id, build.buildtype)
    return build.buildtype


def get_build_id_and_system(build_id):
    build_system = 'ob'
    if '-' in str(build_id):
        temp = build_id.split('-')
        build_id = temp[1]
        build_system = temp[0]
    return build_id, build_system


def get_ova_url(build_id):
    return get_url(build_id, '_OVF10.ova')


def get_patch_url(build_id):
    return get_url(build_id, '_all.deb')


def get_upgrade_url(build_id):
    return get_url(build_id, '-upgrade-')


def get_url(build_id, deliverable_name):
    build = get_build(build_id)
    deliverables = buildapi.ListResource.by_url(build._deliverables_url)
    deliverable = [d for d in deliverables
                   if d.matches(path=deliverable_name)][0]
    LOG.debug('Download URL of %s is %s', build_id, deliverable._download_url)
    return deliverable._download_url


def get_product(build_id):
    build = get_build(build_id)
    LOG.debug('Product of %s is %s.', build_id, build.product)
    return build.product


def download_ova(build_id, path=None):
    ova_url = get_ova_url(build_id)
    return download_file(ova_url, path)


def download_patch(build_id, path=None):
    deb_url = get_patch_url(build_id)
    return download_file(deb_url, path)


def download_upgrade(build_id, path=None):
    deb_url = get_upgrade_url(build_id)
    return download_file(deb_url, path)


def download_file(url, path=None):
    file_name = os.path.basename(url)
    if path:
        abs_path = os.path.join(path, file_name)
    else:
        abs_path = os.path.join(os.getcwd(), file_name)
    if not os.path.exists(abs_path):
        cmd = "wget --no-verbose -O %s %s" % (abs_path, url)
        safe_run(cmd, 'download %s' % url)
        LOG.info('Downloaded %s to %s', url, abs_path)
    else:
        LOG.info('%s already exists, skip downloading it.', abs_path)
    return abs_path


def get_latest_build_url(branch, build_type, product='vmw-openstack'):
    build_id = get_latest_build_id(branch, build_type, product)
    return get_ova_url(build_id)


def get_latest_build_id(branch, build_type, product='vmw-openstack'):
    return buildapi.MetricResource.by_name('build',
                                           product=product,
                                           buildstate='succeeded',
                                           buildtype=build_type,
                                           branch=branch).get_max_id()


def get_build(build_id):
    build_id, build_system = get_build_id_and_system(build_id)
    return buildapi.ItemResource.by_id('build', int(build_id), build_system)


def get_build_version(build_id):
    build = get_build(build_id)
    LOG.debug('Version of %s is %s.', build_id, build.version)
    return build.version
