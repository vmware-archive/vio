import json
import datetime
import logging
import re
import time


from restclient import RestClient


LOG = logging.getLogger(__name__)


class TimeoutError(Exception):
    """Time out exceptions"""


class OMSError(Exception):
    """OMS error"""


class OmsController(object):
    # Helper methods

    def __init__(self, oms, sso_user, sso_pwd):
        self.rest_client = RestClient(oms, sso_user, sso_pwd)
        self.logger = logging.getLogger(__name__)

        self._made_remote_dirs = []

    def login(self):
        self.rest_client.login()

    def hello(self):
        return self.rest_client.do_get('hello')

    def server_version(self):
        return self.rest_client.do_get('version')

    def server_status(self):
        return self.rest_client.do_get('status')

    def list_task(self):
        return self.rest_client.do_get('tasks')

    def list_networks(self):
        response = self.rest_client.do_get("networks")
        return response

    def list_datastores(self):
        response = self.rest_client.do_get("datastores")
        return response

    def list_deployments(self):
        clusters = self.rest_client.do_get('clusters')
        return clusters

    def list_deployment(self, name):
        api_url_template = "cluster/{}"
        url = api_url_template.format(name)
        cluster = self.rest_client.do_get(url)
        return cluster

    def delete_deployment(self, deployment_name):
        resp = self.rest_client.do_delete('cluster', deployment_name)
        return self._validate_task('Delete cluster', resp)

    def create_deployment_by_spec(self, deployment_json, timeout=5400):
        resp = self._create_deployment(deployment_json)
        return self._validate_task('Create cluster', resp, timeout=timeout)

    def _create_deployment(self, spec):
        post_body = json.dumps(spec)
        LOG.debug("Create OpenStack Cluster with spec: %s" % post_body)
        resp = self.rest_client.do_post('clusters', post_body)
        return resp

    def add_compute_vc(self, spec):
        post_body = json.dumps(spec)
        resp = self.rest_client.do_post('vc', post_body)
        return resp

    def get_vc_ip(self):
        resp = self.rest_client.do_get('vcip')
        return resp

    def cluster_config(self, spec):
        resp = self.rest_client.do_put("cluster/VIO/config", spec)
        return resp

    def get_task(self, taskid):
        task = self.rest_client.do_get('task/{}'.format(taskid))
        return json.loads(task.text)

    def del_nova_datastore(self, spec):
        resp = self.rest_client.do_put("clusters/VIO/novadatastore", spec)
        return resp

    def del_glance_datastore(self, spec):
        resp = self.rest_client.do_put("clusters/VIO/glancedatastore", spec)
        return resp

    def edit_cluster(self, cluster, spec, timeout=5400):
        api_url_template = "clusters/%s/edit"
        url = api_url_template % cluster
        put_body = json.dumps(spec)
        resp = self.rest_client.do_put(url, put_body)
        return self._validate_task('Edit cluster', resp, timeout=timeout)

    def retrieve_cluster_profile(self, cluster):
        api_url_template = "clusters/%s/profile"
        url = api_url_template % cluster
        resp = self.rest_client.do_get(url)
        return resp

    def create_deployment_plan(self, spec):
        resp = self.rest_client.do_put("clusters/plan", spec)
        return resp

    def add_nova_node_plan(self, cluster, ng):
        api_url_template = "cluster/{}/nodegroup/{}/plan"
        url = api_url_template.format(cluster, ng)
        resp = self.rest_client.do_put(url, str(2))  # totalInstanceNum
        return resp

    def add_nova_node(self, cluster, ng, spec):
        LOG.debug('Add nova node spec: %s', spec)
        api_url_template = "cluster/{}/nodegroup/{}/scaleout"
        url = api_url_template.format(cluster, ng)
        LOG.debug('Add nova node url: %s', url)
        resp = self.rest_client.do_put(url, spec)
        return self._validate_task('Add nova node', resp)

    def add_node_group(self, cluster, spec):
        api_url_template = "clusters/{}/nodegroups"
        url = api_url_template.format(cluster)
        resp = self.rest_client.do_post(url, spec)
        return resp

    def del_nova_node(self, cluster, ng, nd):
        api_url_template = "cluster/{}/nodegroup/{}/node"
        url = api_url_template.format(cluster, ng)
        resp = self.rest_client.do_delete(url, nd)
        return resp

    def increase_ips(self, nw, spec):
        api_url_template = "network/{}?action=add"
        url = api_url_template.format(nw)
        resp = self.rest_client.do_put(url, spec)
        return resp

    def remove_ips(self, nw, spec):
        api_url_template = "network/{}?action=remove"
        url = api_url_template.format(nw)
        resp = self.rest_client.do_put(url, spec)
        return resp

    def update_dns(self, nw, spec):
        api_url_template = "network/{}/async"
        url = api_url_template.format(nw)
        resp = self.rest_client.do_put(url, spec)
        return resp

    def get_sysconf(self):
        resp = self.rest_client.do_get("conf")
        return json.loads(resp.text)

    def set_syslogserver(self, logserver, port, protocol, tag):
        url = \
            'conf?syslogserver={}&syslogserverport={}' \
            '&syslogserverprotocol={}&syslogservertag={}'
        resp = self.rest_client.do_put(
            url.format(
                logserver, port, protocol, tag), "")
        return resp

    def get_network_by_name(self, networkname):
        resp = self.rest_client.do_get("network/{}".format(networkname))
        return json.loads(resp.text)

    def create_support_bundle(self, spec):
        resp = self.rest_client.do_post("bundles", spec)
        return resp

    def get_support_bundle(self, spec, dest):
        resp = self.rest_client.do_post("bundles", spec)
        fileName = resp.text.split('/')[-1][0:-1]
        with open('%s/%s' % (dest, fileName), 'wb') as handle:
            resp = self.rest_client.do_get("bundle/{}".format(fileName))
            for block in resp.iter_content(1024):
                if not block:
                    break
                handle.write(block)
        return fileName

    def validate(self, type, spec):
        api_url_template = "validators/{}"
        url = api_url_template.format(type)
        put_body = json.dumps(spec)
        resp = self.rest_client.do_post(url, put_body)
        return resp

    def manage_openstack_services(self, cluster, service, action):
        api_url_template = "clusters/{}/services/{}?action={}"
        url = api_url_template.format(cluster, service, action)
        resp = self.rest_client.do_put(url, None)
        return resp

    def start_services(self, cluster, spec):
        api_url_template = "clusters/{}/services?action=start"
        url = api_url_template.format(cluster)
        resp = self.rest_client.do_put(url, spec)
        return resp

    def stop_services(self, cluster, spec):
        api_url_template = "clusters/{}/services?action=stop"
        url = api_url_template.format(cluster)
        resp = self.rest_client.do_put(url, spec)
        return resp

    def restart_services(self, cluster, spec):
        api_url_template = "clusters/{}/services?action=restart"
        url = api_url_template.format(cluster)
        resp = self.rest_client.do_put(url, spec)
        return resp

    def generate_csr(self, clusterName, spec):
        api_url_template = "clusters/{}/csr"
        url = api_url_template.format(clusterName)
        resp = self.rest_client.do_post(url, spec)
        return resp

    def add_horizon(self, cluster, spec):
        api_url_template = "clusters/{}/horizon"
        url = api_url_template.format(cluster)
        resp = self.rest_client.do_post(url, spec)
        return resp

    def del_horizon(self, cluster, title):
        api_url_template = "clusters/{}/horizon"
        url = api_url_template.format(cluster)
        resp = self.rest_client.do_delete(url, title)
        return resp

    def list_horizon(self, cluster):
        api_url_template = "clusters/{}/horizon"
        url = api_url_template.format(cluster)
        regions = self.rest_client.do_get(url)
        return regions

    def get_plugin_status(self):
        url = "plugin/status"
        resp = self.rest_client.do_get(url)
        return resp

    def check_oms_vc_connection(self):
        url = "checkOmsVCConnection"
        resp = self.rest_client.do_get(url)
        return resp

    def get_oms_vc_status(self):
        url = "connection/status"
        resp = self.rest_client.do_get(url)
        return resp

    def register_plugin(self):
        url = "plugin/register?addException=true"
        resp = self.rest_client.do_post(url, "")
        return resp

    def change_datacollector_setting(self, enable="false"):
        api_url_template = "datacollector?enabled={}"
        url = api_url_template.format(enable)
        resp = self.rest_client.do_post(url, "")
        return resp

    def get_datacollector_setting(self):
        url = "datacollector"
        resp = self.rest_client.do_get(url)
        return resp

    def get_audit_file(self):
        url = "phauditfile"
        resp = self.rest_client.do_get(url)
        return resp

    def start_cluster(self, cluster):
        api_url_template = "cluster/%s?action=start"
        url = api_url_template % cluster
        resp = self.rest_client.do_put(url, "")
        return resp

    def stop_cluster(self, cluster):
        api_url_template = "cluster/%s?action=stop"
        url = api_url_template % cluster
        resp = self.rest_client.do_put(url, "")
        return resp

    def retry_cluster(self, cluster, timeout=5400):
        api_url_template = "cluster/%s?action=retry"
        url = api_url_template % cluster
        resp = self.rest_client.do_put(url, "")
        return self._validate_task('Retry cluster', resp, timeout=timeout)

    def upgrade_provision(self, cluster, spec):
        post_body = json.dumps(spec)
        LOG.debug('Green cluster spec: %s', spec)
        api_url_template = '/clusters/%s/upgrade/provision'
        url = api_url_template % cluster
        resp = self.rest_client.do_post(url, post_body)
        return self._validate_task('Create green cluster', resp)

    def upgrade_retry(self, cluster, spec):
        put_body = json.dumps(spec)
        api_url_template = '/clusters/%s/upgrade/retry'
        url = api_url_template % cluster
        resp = self.rest_client.do_put(url, put_body)
        return resp

    def upgrade_migrate_data(self, cluster):
        api_url_template = '/clusters/%s/upgrade/configure'
        url = api_url_template % cluster
        resp = self.rest_client.do_put(url, "")
        return self._validate_task('Migrate blue cluster data', resp)

    def upgrade_switch_to_green(self, cluster):
        api_url_template = '/clusters/%s/upgrade/switch'
        url = api_url_template % cluster
        resp = self.rest_client.do_put(url, "")
        return self._validate_task('Switch to green cluster', resp)

    def switch_keystone_backend(self, cluster, spec):
        put_body = json.dumps(spec)
        api_url_template = '/clusters/%s/keystonebackend'
        url = api_url_template % cluster
        resp = self.rest_client.do_put(url, put_body)
        return resp

    def change_deployment_type(self, newtype):
        api_url_template = '/deploymenttype?deployment_type=%s'
        url = api_url_template % newtype
        resp = self.rest_client.do_post(url, "")
        return resp

    def unconfig_ceilometer(self, cluster):
        api_url_template = '/clusters/%s/unconfigceilometer'
        url = api_url_template % cluster
        resp = self.rest_client.do_put(url, "")
        return self._validate_task('Unconfig ceilometer', resp)

    @staticmethod
    def _get_task_id(url):
        LOG.debug('Grep task id from url: %s', url)
        pattern = re.compile(r'/task/(\d+)')
        result = pattern.search(url)
        if result:
            task_id = result.group(1)
            LOG.debug('Task id: %s' % task_id)
            return task_id

    def wait_for_task_completed(self, task_id, interval=60, timeout=3600):
        begin_poll = datetime.datetime.now()
        status_list = ['COMPLETED', 'STOPPING', 'STOPPED', 'FAILED']
        while (datetime.datetime.now() - begin_poll).seconds < timeout:
            task = self.get_task(task_id)
            if task['status'] in status_list:
                LOG.debug('Task %s status: %s', task_id, task['status'])
                return task['status'], task['errorMessage']
            time.sleep(interval)
        raise TimeoutError('Waited %s seconds for task %s' % (timeout,
                                                              task_id))

    def _validate_task(self, task_name, resp, interval=60, timeout=3600):
        start = time.time()
        LOG.debug('Response header: %s', resp.headers)
        LOG.debug('Response body: %s', resp.text)
        if resp.status_code != 202:
            raise OMSError('Task %s failed: %s' % (task_name, resp.text))
        url = resp.headers['Location']
        LOG.debug('Retrieve redirect url %s of task %s', url, task_name)
        task_id = OmsController._get_task_id(url)
        if not task_id:
            raise OMSError('Task id of %s not found.' % task_name)
        status, msg = self.wait_for_task_completed(task_id, interval, timeout)
        if status != 'COMPLETED':
            raise OMSError('Task %s %s: %s' % (task_name, status, msg))
        end = time.time()
        LOG.debug('Task %s took %s seconds', task_name, (end - start))
        return task_id
