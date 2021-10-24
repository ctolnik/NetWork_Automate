import json
import logging
import os
from configparser import ConfigParser

from xfunctions import normalize_name, write_result_to_json
from send_commands import send_commands_parallel

logging.basicConfig(
    format='%(levelname)s: %(message)s',
    level=logging.INFO)
# Путь к конфигу с хардкодом
CONFIGFILE = '/usr/local/scripts/configs/config.ini'

# Парсим конфигурационный файл
config = ConfigParser()
config.read(CONFIGFILE)
netLogin = config.get('net', 'netLogin', fallback='not exists')
netPassword = config.get('net', 'netPassword', fallback='not exists')
network = config.get('net', 'network', fallback='not exists')
# threads = int(config.get('net', 'threads', fallback='not exists'))
cmdbURL = config.get('cmdb', 'cmdbURL', fallback='not exists')
cmdbLogin = config.get('cmdb', 'cmdbLogin', fallback='not exists')
cmdbPassword = config.get('cmdb', 'cmdbPassword', fallback='not exists')
cmdbObjectSchemaName = config.get(
    'cmdb', 'object_schema_name', fallback='not exists')
cmdbObjectTypeName = config.get(
    'cmdb', 'cmdbObjectTypeName', fallback='not exists')


COMMANDS = {
    "cisco_s300": [('show inventory', False), ('show system', False),
                   ('show lldp neighbors', False), ('show vlan', False),
                   ('show int status', False)],
    'cisco_ios': [('show inter status', False), ('show version', False),
                  ('show lldp neighbors', False), ('show vlan', False)],
    'ruckus_fastiron': [('show lldp neighbors', False),
                        ('show inter brief', False), ('show version', False),
                        ('show vlan', False)],
}


def get_info(devices):
    logging.info("*"*60)
    logging.info("Начало сбора информации с коммутаторов")
    logging.info("*"*60)
    result = {}
    for device in devices:
        ip = device['ip']
        hostname = device['host']
        result[hostname] = {}
    device_types = set([device['device_type'] for device in devices])
    for type in device_types:
        list_type = [
            device for device in devices if device["device_type"] == type]
        logging.info(f"Начало работы с {type}")
        if type == "brocade_fastiron":
            ruckus_commands = COMMANDS["ruckus_fastiron"]
            brocade_inventory = send_commands_parallel(
                list_type, ruckus_commands, limit=len(list_type))
            for record in brocade_inventory:
                for host, output in record.items():
                    result[host] = output
        else:
            commands = COMMANDS[type]
            inventory = send_commands_parallel(
                list_type, commands, limit=len(list_type))
            for record in inventory:
                for host, output in record.items():
                    result[host] = output
    return result


if __name__ == "__main__":
    logging.info("*"*60)
    logging.info("Начало работы скрипта")
    logging.info("*"*60)
    logging.info("Часть 1. Работа с коммутаторами")
    filedump = "/usr/local/scripts/output/x_switches.json"
    if os.path.isfile(filedump):
        with open(filedump) as f:
            switches = json.load(f)

    sw_info = get_info(switches)
    write_result_to_json(sw_info, 'sw_info.json')
    print('Done')
