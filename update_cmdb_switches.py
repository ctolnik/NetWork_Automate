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
CONFIGFILE = 'config.ini'

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


def get_inventory(devices):
    """Подключение к устройствам по NetMiko. Для получения
    информации по серийному номеру, LLDP, модели и др.

    Args:
        devices (dict): Словарь для подключения по NetMiko.
        Созавать данный словарь лучше отдельной функцией или смотри
        документацию по NetMiko что необходимо для подключения

    Returns:
        dict: Словарь устройств. 
        С собранным и обработанным выводом show команд
    """
    # TODO: Сделать проверку имени иногда вывод некоректен.
    logging.info("*"*60)
    logging.info("Начало инвентаризации коммутаторов")
    logging.info("*"*60)
    result = {}
    """
    Создаём словарь для каждого устройства с IP. 
    Имена ключей делаем, как имена атрибутов.
    """
    for device in devices:
        ip = device['ip']
        hostname = device['host']
        result[hostname] = {}
        result[hostname] = {'IP-Address': ip}
        result[hostname].update({'Name': hostname})
        result[hostname].update({'DNS-Name': f"{hostname}.npo.izhmash"})
        result[hostname].update({'IsStack': False})
    device_types = set([i['device_type'] for i in devices])
    """ Подключение к устройствам по их платформе. Т.к. с разным оборудованием
    необходимы разные команды и обработки """

    for type in device_types:
        list_type = [i for i in devices if i["device_type"] == type]
        logging.info(f"Начало работы с {type}")
        if type == "cisco_s300":
            s300_commands = [
                ('show inventory', False), ('show system', True),
                ('show lldp neighbors', False)]

            s300_inventory = send_commands_parallel(
                list_type, s300_commands, limit=len(list_type))
            for record in s300_inventory:
                for host, output in record.items():
                    result[host]['Model'] = output['show system'][0]['model']
                    result[host]['Vendor'] = 'Cisco'
                    match = re.search(r'SN:\s+(\S+)', output['show inventory'])
                    result[host]['Serial Number'] = match.groups()[0]
                    result[host]['lldp'] = output['show lldp neighbors']

        else:
            others_commands = [
                ('show version', True), ('show lldp neighbors detail', False)]
            others_inventory = send_commands_parallel(
                list_type, others_commands, limit=len(list_type))

            for record in others_inventory:
                for host, output in record.items():
                    version = output['show version']
                    if type == "cisco_ios":
                        result[host]['Vendor'] = 'Cisco'
                        result[host]['Serial Number'] = version[0]['serial'][0]
                        result[host]['Model'] = version[0]['hardware'][0]
                    elif type == "brocade_fastiron":
                        result[host]['Serial Number'] = version[0]['serial'][0]
                        result[host]['Model'] = version[
                            0]['hw'].split()[-1]

                        result[host]['Vendor'] = 'Brocade'
                    else:
                        result[host]['Model'] = version[
                            0]['hardware'].split()[-1]
                        result[host]['Vendor'] = 'Ruckus'

                        if len(version[0]['serial']) < 2:
                            result[host]['Serial Number'] = version[
                                0]['serial'][0]
                        else:
                            # Если попало сюда, то это стек
                            # TODO: rethink
                            result[host]['IsStack'] = True
                            stack_members = []
                            for i in range(len(version[0]['serial'])):
                                sn = version[0]['serial'][i]
                                hostname = f"{host}_{i+1}"
                                result[hostname] = {}
                                result[hostname]['Serial Number'] = sn
                                result[hostname]['Name'] = hostname
                                result[hostname]['DNS-Name'] = f"{hostname}.npo.izhmash"
                                result[hostname]['Model'] = version[
                                    0]['hardware'].split()[-1]
                                result[hostname]['Vendor'] = 'Ruckus'
                                stack_members.append(hostname)
                            result[host]['Stack Members'] = stack_members
                    result[host]['lldp'] = output['show lldp neighbors detail']
        logging.info(f"Опрос {type} завершён")
    return result


def build_topology(switches):
    """Определение Parent коммутатора

    Args:
        switches (dict): Возвращение устройств с Parent unit
    """
    # TODO: Hardcode убрать.
    core = 'x-SW-ZU-COR-01'
    switches[core]['Parent unit'] = {}
    logging.info(f"Для {core} задано пустое значение.")

# В этот список будут добавляться устройства для обработки
    check_devices = []
    logging.info("-"*50)
    logging.info(f"Парсинг LLDP информации устройств")
    logging.info("-"*50)

    for switch in switches:
        if switches[switch].get('lldp'):
            # Ищем все записи начинающиеся с 'x-S'
            # TODO: Hardcode убрать.
            connected_devices = re.finditer(
                r'(x-S\S+)', switches[switch]['lldp'])
            list_connected_dev = []
            for system_name in connected_devices:
                name = system_name.group(1)
                name = normalize_name(name)
                list_connected_dev.append(name)
            switches[switch]['lldp'] = list_connected_dev

    logging.info("-"*50)
    logging.info(f"Парсинг LLDP завершен")
    logging.info("-"*50)
    logging.info(f"Обработка подключенных к {core} устройств.")
    logging.info("-"*50)

    # Перебираем устройства 1-ого уровня. Подключенных к ядру.
    for switch in switches[core]['lldp']:
        logging.info(f"Обработка {switch} подключенного к {core}")
        switches[switch]['Parent unit'] = core
        check_devices.append(switch)

    logging.info(f"Обработка устройств подключенных к {core} завершена")
    logging.info("-"*50)
    logging.info(
        f"Перебор списка из {len(check_devices)} устройств на проверку")
    # Перебор устройств перевого уровня с добавлением следующих уровней
    for check_device in check_devices:
        logging.info(f"Обработка {check_device}")
        for linked_device in switches[check_device]['lldp']:
            if switches.get(linked_device):
                if switches[linked_device].get('Parent unit') is None:
                    logging.info(
                        f"{linked_device} указываем Parent Unit и на проверку")
                    switches[linked_device]['Parent unit'] = check_device

                    # Проверка, что есть LLDP с данного устройства.

                    if switches[check_device]['lldp'] is not None:
                        check_devices.append(linked_device)
                    else:
                        logging.info(f"По {check_device} отсутствует LLDP.")
                else:
                    logging.info(
                        f"""{linked_device} уже имеет UpLink на
                        {switches[linked_device]['Parent unit']}""")

        logging.info(f"{check_device} обработан")
        logging.info("-"*50)
    logging.info("Завершено. Построен словарь UpLink устройств.")
    logging.info(f"В словаре {len(switches)} устройств.")
    logging.info("-"*50)
    logging.info(f"Cleaning")
    del switches[core]['Parent unit']
    for device in switches:
        if switches[device].get('lldp'):
            del switches[device]['lldp']
    return switches


def build_json(devices):

    # Добавление ролей
    for device in devices:
        # Temp
        if devices[device].get('lldp'):
            del devices[device]['lldp']

        devices[device]['Services'] = "Локальная сеть"
        location = device.split('-')[2]
        devices[device]['Location'] = location
        if 'ACS' in device:
            devices[device]['Switch Role'] = "Доступ"
        elif 'DiS' in device or 'DiS' in device:
            devices[device]['Switch Role'] = "Агрегация"
        elif 'COR' in device:
            devices[device]['Switch Role'] = "Ядро"
        elif 'MGMT' in device:
            devices[device]['Switch Role'] = "Доступ"
    return devices


if __name__ == "__main__":
    logging.info("*"*60)
    logging.info("Начало работы скрипта")
    logging.info("*"*60)
    logging.info("Часть 1. Работа с коммутаторами")
    filedump = "/usr/local/scripts/output/x_switches.json"
    if os.path.isfile(filedump):
        with open(filedump) as f:
            x_switches = json.load(f)
    else:
        x_switches = build_device_list(
            network, netLogin, netPassword, filedump)
    inventory_data = get_inventory(x_switches)
    # write_result_to_json(inventory_data, filedump)

    logging.info("Работа с коммутаторами завершена")
    logging.info("*"*60)
    logging.info("Часть 2. Обработка полученной информации")
    logging.info("*"*60)
    topology = build_topology(inventory_data)
    write_result_to_json(cmdb_json, 'cmdb.json')
    logging.info("Обработка завершена")
    logging.info("*"*60)
    logging.info("Часть 3. Начинаем работу с CMDB")
    logging.info("*"*60)

# Список всех объектов по типу объекта - "Ethernet Switches[x]"
    objectList = get_objectinsight(
        cmdbURL, cmdbObjectSchemaName, cmdbLogin,
        cmdbPassword, cmdbObjectTypeName)

# Загрузка информации по производителям для заполнения Vendor у устройств.
    models_cmdb = get_objectinsight(
        cmdbURL, cmdbObjectSchemaName, cmdbLogin,
        cmdbPassword, "Model Switches[x]")

# Список атрибутов по типу объекта - "Ethernet Switches[x]"
    objtypeattrlist = objectList['objectTypeAttributes']

# Определяем ID у типа объекта - "Ethernet Switches[x]"
    ObjectTypeID = get_objecttypes(
        cmdbURL, cmdbObjectSchemaName, cmdbLogin, cmdbPassword,
        cmdbObjectTypeName)[0]['id']

    logging.info("Обработка завершена")
    logging.info("*"*60)
    logging.info(
        "Часть 4. Заставляем CMDB и сетевые устройства ебаться вместе")
    logging.info("*"*60)

    for device, params in cmdb_json.items():
        logging.info(f"Начинаю работу с {device}")

        ObjectFromCMDB = None
        ObjectFromCMDB = [
            object for object in objectList['objectEntries']
            if object['name'] == device]

        update_objectinsight(
            cmdbURL, cmdbObjectSchemaName, ObjectFromCMDB, objtypeattrlist,
            cmdbObjectTypeName, cmdbLogin, cmdbPassword, params, ObjectTypeID)
    logging.info("*"*60)
    logging.info("Завершение работы скрипта")
    logging.info("*"*60)
