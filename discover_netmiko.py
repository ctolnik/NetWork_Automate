#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import nmap3
from netmiko import ConnectHandler
from netmiko.ssh_exception import (NetMikoAuthenticationException,
                                   NetmikoTimeoutException)
from xfunctions import normalize_name, write_result_to_json

logging.getLogger("paramiko").setLevel(logging.WARNING)
logging.basicConfig(
    format='%(threadName)s %(name)s %(levelname)s: %(message)s',
    level=logging.INFO)

start_msg = '===> {} Соединение: {}'
received_msg = '<=== {} Получен: {}'
DEVICE_PLATFROMS = 'devices_platforms.json'


def send_show(device, command):
    """Отправка show, используя NetMiko. Для создания словарей.

    Args:
        device (dict): Словарь с параметрами устройства
        command (str): Команда для выполнения по SSH.
        Например, 'show version'

    Returns:
        [dict]: Вывод команды с IP. device: output
    """
    output = ""
    ip = device['host']
    logging.info(start_msg.format(datetime.now().time(), ip))
    try:
        prompt = ip
        with ConnectHandler(**device) as ssh:
            output = ssh.send_command(command)
            prompt = ssh.find_prompt()
            logging.info(received_msg.format(datetime.now().time(), ip))
    except (NetmikoTimeoutException, NetMikoAuthenticationException):
        logging.warning(ip)
    except OSError:
        logging.warning(f"Ошибка OSError у {ip}. Меняем device_type")
        device["device_type"] = "cisco_s300"
        with ConnectHandler(**device) as ssh:
            output = ssh.send_command("show system")
            prompt = ssh.find_prompt()
            logging.info(received_msg.format(datetime.now().time(), ip))

    if output:
        return {ip: [prompt, output]}
    return {ip: ""}
    logging.error(f"Исключён {ip} из результата функции. Не получен вывод.")


def generate_list_connet(iplist, login, password, limit=80):
    """Создаёт список словарей для передачи на подключение Netmiko

    Args:
        iplist (list): список IP-адресов коммутаторов
        login (str): Логин для подключения по SSH к коммутаторам
        password (str): Пароль для подключения по SSH к коммутаторам

    Returns:
        [dict]: словарь с персонализированными настройками для подключения
        к коммутаторам
    """
    # генерация списка для перебора на основе списка IP-адресов
    startTime = time.time()
    logging.info("*"*60)
    logging.info("Генерация словарей для SSH-подключений")
    logging.info("*"*60)
    result = []
    devices = [
        {
            "device_type": "cisco_ios",
            "host": ip,
            "username": login,
            "password": password,
        }
        for ip in iplist
    ]
    if os.path.isfile(DEVICE_PLATFROMS):
        with open(DEVICE_PLATFROMS) as f:
            devices_platforms = json.load(f)

    # Сбор информации с устройств в потоках. Кол-во по умолчанию 80
    with ThreadPoolExecutor(max_workers=limit) as executor:
        result_all = [
            executor.submit(send_show, device, "show version")
            for device in devices]
    # По мере получения результата обработка данных

        for f in as_completed(result_all):
            data = f.result()
            logging.info(f'Future done {f}')
    # Исключение устройств без вывода
            working = {key: value for key, value in data.items() if value}
            for ip, output in working.items():
                dict = {}
                dict['host'] = normalize_name(output[0])
    # Определяем тип устройства
                # output[1] = output[1].split()
                # for word in output[1]:
                #     if word in devices_platforms:
                #         device_type = devices_platforms[word]
                #     else:
                #         device_type = "cisco_s300"
                if "Ruckus" in output[1]:
                    device_type = "ruckus_fastiron"
                elif "Brocade" in output[1]:
                    device_type = "brocade_fastiron"
                elif "Cisco IOS Software" in output[1]:
                    device_type = "cisco_ios"
                elif "Aruba" in output[1]:
                    device_type = "cisco_ios"
                else:
                    device_type = "cisco_s300"
                dict["device_type"] = device_type
                dict["ip"] = ip
                dict["username"] = login
                dict["password"] = password
                result.append(dict)

    runtime = float("%0.2f" % (time.time() - startTime))
    logging.info("*"*60)
    logging.info(
        f"Словарь на {len(result)} устройств собран, за {runtime} секунд"
    )
    logging.info("*"*60)
    return result


def build_device_list(ip_net, login: str, password: str, filedump=None):
    """Основная функция. Сканирует nmap диапазон сети.
    Передаёт живые хосты функции generate_list_connet,
    которая формирует словарь подюключений и возвращает в эту функцию.

    Args:
        ip_net (str): IP диапазон в формате 10.0.0.0/24
        login (str): логин для подключения на коммутаторы
        password (str): пароль для подключения на коммутаторы
        filedump (str, optional): Сохранение результата в JSON файл.
        Defaults to None.

    Returns:
        [dict]: Словарь с настройками для подключения NetMiko
    """
    subnet = scan_network(ip_net)
    if subnet is None:
        return "Нет адресов для сканирования"
    switches = generate_list_connet(subnet, login, password, len(subnet))
    if filedump:
        write_result_to_json(switches, filedump)
    logging.info(f"Завершено. Устройств для работы {len(switches)}")
    return switches


def scan_network(ip_net: str):
    nmap = nmap3.NmapScanTechniques()
    nmap_scan = nmap.nmap_ping_scan(ip_net)
    network = [ip for ip in nmap_scan if '.' in ip]
    logging.info("*"*80)
    logging.info(f"Доступно IP - {len(network)}. В сети {ip_net}")
    logging.info("*"*80)
    if len(network) == 0:
        return None
    return network


if __name__ == "__main__":
    vlan_mgmt_3 = "10.26.0.0/24"
    print('Done')
