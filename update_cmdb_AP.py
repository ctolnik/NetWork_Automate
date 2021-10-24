# -*- coding: utf-8 -*-
import json
import logging
import os
import re
from configparser import ConfigParser

import jirainsight
from discovernetmiko import build_device_list
from send_commands import send_commands_parallel
from xfunctions import normalize_name, write_result_to_json

# Настройки логирования
logging.basicConfig(
    format='%(levelname)s: %(message)s',
    level=logging.INFO)
# Путь к конфигу
CONFIGFILE = '/usr/local/scripts/configs/config_ap.ini'

# Парсим конфигурационный файл
config = ConfigParser()
config.read(CONFIGFILE)
netLogin = config.get('net', 'wifi_login', fallback='not exists')
netPassword = config.get('net', 'wifi_password', fallback='not exists')
network = config.get('net', 'network', fallback='not exists')
# threads = int(config.get('net', 'threads', fallback='not exists'))
cmdbURL = config.get('cmdb', 'cmdbURL', fallback='not exists')
cmdbLogin = config.get('cmdb', 'cmdbLogin', fallback='not exists')
cmdbPassword = config.get('cmdb', 'cmdbPassword', fallback='not exists')
cmdbObjectSchemaName = config.get(
    'cmdb', 'object_schema_name', fallback='not exists')
cmdbObjectTypeName = config.get(
    'cmdb', 'cmdbObjectTypeName', fallback='not exists')


def parse_data(search, data):
    match = re.search(search, data)
    if match:
        return match.groups()[0]


def get_inventory(devices):

    # TODO: Сделать проверку имени иногда вывод некоректен.
    logging.info("*"*60)
    logging.info("Начало инвентаризации ...")
    logging.info("*"*60)
    result = {}
    """
    Создаём словарь для каждого устройства с IP. 
    Имена ключей делаем, как имена атрибутов.
    """
    for device in devices:
        ip = device['ip']
        hostname = device['host']
        hostname = hostname.split('_')[0]
        result[hostname] = {}
        # result[hostname] = {'IP-Address': ip}
        result[hostname].update({'Name': hostname})
        result[hostname].update({'DNS-Name': f"{hostname}.npo.izhmash"})
        result[hostname].update({'Vendor': "HP"})

    inventory = [
        ('show version', False), ('show summary', False),
        ('show ap debug lldp neighbor interface bond0', False),
        ('show interface', False)
    ]

    get_info = send_commands_parallel(
        devices, inventory, limit=len(devices))

    for record in get_info:
        for host, output in record.items():
            host = host.split('_')[0]
            model = parse_data('MODEL:\s+(\S+)\)', output['show version'])
            result[host]['Model'] = model
            # name = parse_data('Name\s+:(\S+)', output['show summary'])
            location = parse_data(
                'System Location\s+:(\S+ \S+)', output['show summary'])
            result[host]['Location'] = location
            ip = parse_data("\nIP Address\s+:(\S+)", output['show summary'])
            result[host]['IP-Address'] = ip
            mac = parse_data('address is\s+(\S+)', output['show interface'])
            mac = mac.replace(':', '-')
            result[host]['MAC-address Ethernet'] = mac
            sn = parse_data('Serial Number\s+:(\S+)', output['show summary'])
            result[host]['Serial Number'] = sn
            parent = parse_data(
                'System name:\s+(\S+)',
                output['show ap debug lldp neighbor interface bond0']
            )
            parent = normalize_name(parent)
            result[host]['Parent unit'] = parent
    return result


def build_json(devices):
    for device in devices:

        devices[device]['Services'] = "Wi-Fi"
        location = device.split('-')[2]
        devices[device]['Location'] = location
        devices[device]['IsDeployed'] = 'В эксплуатации'
    return devices


if __name__ == "__main__":
    logging.info("*"*60)
    logging.info("Начало работы скрипта")
    logging.info("*"*60)

    logging.info("Часть 1. Работа с AP")
    filedump = "x_AP.json"

    if os.path.isfile(filedump):
        with open(filedump) as f:
            network_devices = json.load(f)
    else:
        network_devices = build_device_list(
            network, netLogin, netPassword, filedump)
    inventory_data = get_inventory(network_devices)

    # write_result_to_json(inventory_data, filedump)

    logging.info("Работа с коммутаторами завершена")
    logging.info("*"*60)
    logging.info("Часть 2. Обработка полученной информации")
    logging.info("*"*60)

    ap_json = build_json(inventory_data)

    logging.info("Обработка завершена")
    logging.info("*"*60)
    logging.info("Часть 3. Начинаем работу с CMDB")
    logging.info("*"*60)

    raw_list = [device for device in ap_json.values()]

    jira = jirainsight.Insight(cmdbURL, cmdbLogin, cmdbPassword)
    schema = jirainsight.InsightSchema(jira, cmdbObjectSchemaName)
    schema_obj_type = schema.get_object_type(cmdbObjectTypeName)

    source = jirainsight.DataSource(raw_list, schema_obj_type)
    mixer = jirainsight.Mixer(source, schema)
    update_objects = mixer.make_dicts_for_update_schema_objects()
    failed = []
    for key, value in update_objects.items():
        mixer.object_type.objects
        schema_object = mixer.object_type.objects[key]
        try:
            schema_object.update_object(value)
        except Exception as e:
            print(e)
            print(e.response.content)
            failed.append(key)

    logging.info("*"*60)
    logging.info("Завершение работы скрипта")
    logging.info("*"*60)
