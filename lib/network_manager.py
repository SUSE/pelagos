import json
import logging

logging.basicConfig(format='%(asctime)s | %(name)s | %(message)s',
                    level=logging.DEBUG)


data_file = '../networks_info/nue_ses_network.json'


def load_data_file():
#    data = []
    with open(data_file) as json_file:
        data = json.load(json_file)
    return data


def get_node_by_name(name, exception=True):
    for n in load_data_file():
        logging.debug('Process node: ' + n['node'])
        if n['node'] == name:
            return n
    if exception:
        raise Exception("Node [{}] not found".format(name))
    return ""

