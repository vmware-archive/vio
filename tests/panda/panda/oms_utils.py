import logging
import os
import sys
import time

from shellutil import shell
from omsclient.oms_controller import OmsController
from sshutil.remote import RemoteClient
from pyVmomiwrapper import vmwareapi
from exceptions import NotSupportedError, NotCompletedError
import task_utils


LOG = logging.getLogger(__name__)
DEFAULT_LOCAL_OVF_TOOL_PATH = '/usr/bin/ovftool'
OMJS_PATH = '/opt/vmware/vio/etc/omjs.properties'


def get_ovf_tool_path():
    platform = sys.platform
    os.environ['TCROOT'] = "/build/toolchain/"

    if platform.startswith('linux'):
        path = 'lin64'
    elif platform.startswith('win'):
        path = 'win64'
    elif platform.startswith('darwin'):
        path = 'mac32'
    else:
        LOG.debug("unsupported platform %s" % platform)
        return None
    ovf_path = os.environ['OVF_TOOL'] = "%s/%s/ovftool-4.1.0/ovftool" \
                                        % (os.environ['TCROOT'], path)
    if os.path.isfile(ovf_path):
        # check if file exists
        LOG.debug("ovf tool exists at the following location: %s" % ovf_path)
    else:
        LOG.debug("couldn't not find ovftool in toolchain %s " % ovf_path)
        ovf_path = None
    return ovf_path


def wait_for_mgmt_service(oms_ip, vc_user, vc_password):
    LOG.info('Waiting for management service')
    task_utils.wait_for(func=OmsController, timeout=500, delay=10, oms=oms_ip,
                        sso_user=vc_user, sso_pwd=vc_password)
    LOG.info('Management service is running.')


def deploy_vapp(vc_host, vc_user, vc_password, dc, cluster, ds, network,
                ova_path, ntp_server=None, viouser_pwd='vmware', log_path=None,
                ip=None, netmask=None, gateway=None, dns=None,
                ovf_tool_path=None):
    if not ovf_tool_path:
        ovf_tool_path = get_ovf_tool_path()
        if not ovf_tool_path:
            ovf_tool_path = DEFAULT_LOCAL_OVF_TOOL_PATH
    if not os.path.isfile(ovf_tool_path):
        LOG.error('ovftool not found.')
        raise NotSupportedError('ovftool not found')
    if not log_path:
        log_path = os.getcwd()

    ntp_config = '--prop:ntpServer=%s ' % ntp_server if ntp_server else ''
    dns_config = '--prop:vami.DNS.management-server=%s ' % dns if dns else ''
    # deploy ova and poweron vm
    # TODO: implement deploy with dhcp
    cmd = ('"%s" --X:"logFile"="%s/deploy_oms.log" '
           '--vService:"installation"='
           '"com.vmware.vim.vsm:extension_vservice" '
           '--acceptAllEulas --noSSLVerify --powerOn '
           '--datastore=%s '
           '-dm=thin '
           '--net:"VIO Management Server Network"="%s" '
           '--prop:vami.ip0.management-server=%s '
           '--prop:vami.netmask0.management-server=%s '
           '--prop:vami.gateway.management-server=%s '
           '%s '
           '--prop:viouser_passwd=%s '
           '%s %s vi://%s:%s@%s/%s/host/%s'
           '' % (ovf_tool_path, log_path, ds, network, ip, netmask,
                 gateway, dns_config, viouser_pwd, ntp_config, ova_path,
                 vc_user, vc_password, vc_host, dc, cluster))
    LOG.info('Start to deploy management server.')
    # LOG.info(cmd)
    # exit_code = os.system(cmd)
    exit_code = shell.local(cmd)[0]
    if exit_code:
        LOG.warning('Failed to deploy vApp. Retry deploying after 3 minutes.')
        time.sleep(60 * 3)
        shell.local(cmd, raise_error=True)
    wait_for_mgmt_service(ip, vc_user, vc_password)
    LOG.info('Successfully deployed management server.')


def check_vapp_exists(vc_host, vc_user, vc_password,
                      name_regex=r'^VMware-OpenStack.*\d$'):
    with vmwareapi.VirtualCenter(vc_host, vc_user, vc_password) as vc:
        vapp = vc.get_entity_by_regex(vmwareapi.Vapp, name_regex)
    return True if vapp else False


def set_omjs_value(ssh_client, key, value, path=OMJS_PATH):
    ssh_client.run('sed -i "s|%s.*|%s = %s|g" %s' %
                   (key, key, value, path), sudo=True, raise_error=True)


def config_omjs(ip, vc_user, vc_password, properties, user='viouser',
                password='vmware'):
    LOG.info('Update omjs.properties: %s', properties)
    ssh_client = RemoteClient(ip, user, password)
    for key in properties:
        set_omjs_value(ssh_client, key, properties[key])
    ssh_client.run('restart oms', sudo=True, raise_error=True)
    wait_for_mgmt_service(ip, vc_user, vc_password)


def config_omjs_for_release_build(ip, vc_user, vc_password):
    params = {'oms.use_linked_clone': 'true',
              'oms.skip_cluster_vmotion_check': 'true',
              'oms.disable_datastores_anti_affinity': 'true',
              'oms.disable_hosts_anti_affinity': 'true'}
    config_omjs(ip, vc_user, vc_password, params)


def remove_vapp(vc_host, vc_user, vc_password, name_regex):
    with vmwareapi.VirtualCenter(vc_host, vc_user, vc_password) as vc:
        vapp = vc.get_entity_by_regex(vmwareapi.Vapp, name_regex)
        if vapp:
            LOG.info("Start to remove %s" % vapp.name)
            state = vapp.get_state()
            if state == 'started':
                vapp.poweroff()
            vapp.destroy()
        else:
            LOG.info("%s not found" % name_regex)


def get_vapp_version(vc_host, vc_user, vc_password, name_regex):
    with vmwareapi.VirtualCenter(vc_host, vc_user, vc_password) as vc:
        vapp = vc.get_entity_by_regex(vmwareapi.Vapp, name_regex)
        return vapp.version if vapp else None


def get_patch_info(output, patch_version):
    lines = output.split('\n')[2:]
    for line in lines:
        if line.strip():
            items = line.split()
            if patch_version == items[1]:
                LOG.debug('Find patch info: %s' % line)
                return {'Name': items[0],
                        'Version': items[1],
                        'Type': items[2],
                        'Installed': items[-1]}
    raise NotSupportedError('Patch %s not added' % patch_version)


def apply_patch(ip, file_path, user='viouser', password='vmware'):
    file_name = os.path.basename(file_path)
    patch_name, patch_version = file_name.split('_')[0:2]
    LOG.info('Start to Apply patch %s' % patch_version)
    ssh_client = RemoteClient(ip, user, password)
    ssh_client.run('viopatch add -l %s' % file_path, sudo=True,
                   raise_error=True, log_method='info')
    ssh_client.run('viopatch install --patch %s --version %s --as-infra' %
                   (patch_name, patch_version), sudo=True, raise_error=True,
                   log_method='info', feed_input='Y')
    output = ssh_client.run('viopatch list', sudo=True, raise_error=True,
                            log_method='info')
    patch_info = get_patch_info(output, patch_version)
    if patch_info['Installed'] != 'Yes':
        LOG.error('Applying patch failed. %s' % patch_info)
        raise NotCompletedError('Applying %s failed.' % file_path)
    LOG.info('Successfully Applied patch %s' % patch_version)
