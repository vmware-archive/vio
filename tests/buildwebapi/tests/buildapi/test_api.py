from buildwebapi import api as buildapi

import mock
import json
import os
import unittest
import urlparse

RESOURCES_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'resources/buildapi')


def _get(*args, **kwargs):
    payload = None
    p = urlparse.urlparse(args[0])
    if p.path == '/ob/build':
        payload = os.path.join(RESOURCES_PATH, 'buildlist.json')
    elif p.path == '/ob/deliverable':
        payload = os.path.join(RESOURCES_PATH, 'deliverable.json')
    elif p.path == '/ob/build_metrics':
        payload = os.path.join(RESOURCES_PATH, 'buildmetrics.json')
    elif p.path == '/ob/build/1929854':
        payload = os.path.join(RESOURCES_PATH, 'build.json')

    if payload:
        with open(payload) as f:
            return json.load(f)


class ApiTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.patcher = mock.patch('buildwebapi.api._get', _get)
        cls.patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()


class TestListResource(ApiTest):

    def testByName(self):
        builds = buildapi.ListResource.by_name(
            'build', product='vmw_openstack')
        for build in builds:
            self.assertEqual('build', build._this_resource)

    def testByUrl(self):
        url = 'http://buildapi.eng.vmware.com/ob/deliverable?build=1935022'
        deliverables = buildapi.ListResource.by_url(url)
        for deliverable in deliverables:
            self.assertEqual('deliverable', deliverable._this_resource)


class TestMetricResource(ApiTest):

    def testByName(self):
        build_metrics = buildapi.MetricResource.by_name(
            'build', product='vmw_openstack', buildstate='succeeded')
        self.assertEqual(1935022, build_metrics.get_max_id())
        self.assertEqual(1924554, build_metrics.get_min_id())


class TestItemResource(ApiTest):

    def testById(self):
        build_id = 1929854
        build = buildapi.ItemResource.by_id('build', build_id)
        self.assertEqual(build_id, build.id)


if __name__ == '__main__':
    unittest.main()
