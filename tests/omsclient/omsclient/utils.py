import datetime
import logging
import re
import time


LOG = logging.getLogger(__name__)


class TimeoutError(Exception):
    """Time out exceptions"""


class NotFoundError(Exception):
    """Not found exceptions"""


class TaskError(Exception):
    """Task status exceptions"""


def get_task_id(url):
    LOG.debug('Grep task id from url: %s', url)
    pattern = re.compile(r'/task/(\d+)')
    result = pattern.search(url)
    if result:
        task_id = result.group(1)
        LOG.debug('Task id: %s' % task_id)
        return task_id
    else:
        raise NotFoundError('Can not get task id from url %s', url)


def wait_for_task_completed(oms_ctl, task_id, delay=30, timeout=1200):
    begin_poll = datetime.datetime.now()
    status_list = ['COMPLETED', 'STOPPING', "STOPPED", 'FAILED']
    while (datetime.datetime.now() - begin_poll).seconds < timeout:
        task = oms_ctl.get_task(task_id)
        if task['status'] in status_list:
            LOG.debug('Task %s status: %s', task_id, task['status'])
            return task['status'], task['errorMessage']
        time.sleep(delay)
        timeout -= delay
    raise TimeoutError('Waited %s seconds for task %s' % (timeout, task_id))


def validate_task_succeeded(oms_ctl, task_name, resp, delay=30, timeout=1200):
    LOG.debug('Responce header: %s', resp.headers)
    LOG.debug('Responce body: %s', resp.text)
    if resp.status_code != 202:
        raise TaskError('%s failed: %s' % (task_name, resp.text))
    url = resp.headers['Location']
    LOG.debug('Retrieve %s from response of %s', url, task_name)
    task_id = get_task_id(url)
    status, msg = wait_for_task_completed(oms_ctl, task_id, delay, timeout)
    if status != 'COMPLETED':
        raise TaskError('%s failed: %s' % (task_name, msg))
