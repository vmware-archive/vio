import os
import json
import logging.config


def setup_logging(log_cfg='logging.json', env_key='LOG_CFG', log_file=None):
    value = os.getenv(env_key, None)
    if value:
        path = value
    elif os.path.exists(log_cfg):
        path = log_cfg
    else:
        path = "%s/data/logging.json" % \
               os.path.dirname(os.path.abspath(__file__))
    with open(path) as fh:
        dict_conf = json.load(fh)
    if log_file:
        dict_conf['handlers']['file_handler']['filename'] = log_file
    logging.config.dictConfig(dict_conf)
