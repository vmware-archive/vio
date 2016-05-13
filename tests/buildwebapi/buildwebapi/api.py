import itertools
import json
import logging
import requests

BUILDAPI_URL = 'http://buildapi.eng.vmware.com'
BUILDAPI_LIST_RESOURCE_URL = BUILDAPI_URL + '/%s/%s'
BUILDAPI_METRICS_RESOURCE_URL = BUILDAPI_URL + '/%s/%s_metrics'
BUILDAPI_ITEM_RESOURCE_URL = BUILDAPI_URL + '/%s/%s/%d'

DEFAULT_PARAMS = {'_format': 'json'}

LOG = logging.getLogger(__name__)


def _make_params(**kwargs):
    return dict(itertools.chain(DEFAULT_PARAMS.items(), kwargs.items()))


def _get(*args, **kwargs):
    LOG.debug('url: %s' % args[0])
    resp = requests.get(*args, **kwargs)
    LOG.debug('response: \n %s' % resp.text)
    return json.loads(resp.text)


class _Resource(object):
    def __init__(self, data):
        self._data = data

    def __getattr__(self, name):
        return self._data[name]


class ListResource(_Resource):

    @classmethod
    def by_url(cls, url):
        if not url.startswith(BUILDAPI_URL):
            url = BUILDAPI_URL + url
        return cls(_get(url, params=_make_params()))

    @classmethod
    def by_name(cls, name, build_system='ob', **filters):
        url = BUILDAPI_LIST_RESOURCE_URL % (build_system, name)
        return cls(_get(url, params=_make_params(**filters)))

    def __init__(self, data):
        assert '_total_count' in data and '_list' in data
        super(ListResource, self).__init__(data)
        self.items = self._parse_items()

    def __iter__(self):
        return iter(self.items)

    def _parse_items(self):
        return [ItemResource(data) for data in self._data['_list']]


class MetricResource(_Resource):

    @classmethod
    def by_name(cls, name, build_system='ob', **filters):
        url = BUILDAPI_METRICS_RESOURCE_URL % (build_system, name)
        return cls(_get(url, params=_make_params(**filters)))

    def __init__(self, data):
        assert '_total_count' in data and data['_total_count'] == 1
        assert '_list' in data
        assert 'max_id' in data['_list'][0]
        assert 'min_id' in data['_list'][0]
        super(MetricResource, self).__init__(data)

    def get_max_id(self):
        return self._data['_list'][0]['max_id']

    def get_min_id(self):
        return self._data['_list'][0]['min_id']


class ItemResource(_Resource):

    @classmethod
    def by_id(cls, name, res_id, build_system='ob'):
        url = BUILDAPI_ITEM_RESOURCE_URL % (build_system, name, res_id)
        return cls(_get(url, params=_make_params()))

    def __init__(self, data):
        assert '_this_resource' in data
        super(ItemResource, self).__init__(data)

    def matches(self, **filters):
        for k, v in filters.items():
            if not hasattr(self, k):
                return False
            selfv = getattr(self, k)
            is_substring = (isinstance(v, basestring) and (v in selfv))
            is_equals = (v == selfv)
            if not (is_substring or is_equals):
                return False
        else:
            return True
