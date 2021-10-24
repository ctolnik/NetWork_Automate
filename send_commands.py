import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from netmiko import ConnectHandler

logging.getLogger("paramiko").setLevel(logging.WARNING)
logging.basicConfig(
    format='%(threadName)s %(name)s %(levelname)s: %(message)s',
    level=logging.INFO)
start_msg = '===> {} Отправка: {}'
received_msg = '<=== {} Получение: {}'


def send_show_command(device, command, textfsm=True):
    """Отправка команды show на устройство

    Args:
        device (dict): Парметры устройства для подключения
        command (str): команда отправляемая на устройство
        textfsm (bool, optional): Использовать TextFSM. Defaults to True.

    Returns:
        dict: hostname: вывод команды show
    """

    if "NET_TEXTFSM" not in os.environ:
        os.environ["NET_TEXTFSM"] = "/usr/local/scripts/templates"

    ip = device['ip']
    host = device['host']
    logging.info(start_msg.format(datetime.now().time(), ip))
    with ConnectHandler(**device) as ssh:
        output = ssh.send_command(command, use_textfsm=textfsm)
        logging.info(received_msg.format(datetime.now().time(), ip))
    return {host: output}


def send_command_parallel(devices, command, limit=50, textfsm=True):
    """Отправка одной команды show на устройства в несколько потоков

    Args:
        devices (list): Список словарей содержащие информацию для подключения
        command (str): команда отправляемая на устройства
        limit (int, optional): Количество потоков. Defaults to 50.
        textfsm (bool, optional): Использовать TextFSM. Defaults to True.

    Returns:
        [list]: список словарей ключ - ip. Значение вывод с устройства
    """
    with ThreadPoolExecutor(max_workers=limit) as executor:
        result_all = [
            executor.submit(send_show_command, device, command, textfsm)
            for device in devices
        ]
        output = [f.result() for f in as_completed(result_all)]

    return output


def send_commands_parallel(devices, commands, limit=50):
    """Отправка нескольких команд show на устройства в несколько потоков

    Args:
        devices (list): Список словарей содержащие информацию для подключения
        command (str): команда отправляемая на устройства
        limit (int, optional): Количество потоков. Defaults to 50.
        textfsm (bool, optional): Использовать TextFSM. Defaults to True.

    Returns:
        [list]: список словарей ключ - ip. Значение вывод с устройства
    """
    with ThreadPoolExecutor(max_workers=limit) as executor:
        result_all = [
            executor.submit(send_commands, device, commands)
            for device in devices
        ]
        output = [f.result() for f in as_completed(result_all)]

    return output


def send_commands(device, commands):
    """Отправка нескольких команд show на устройства

    Args:
        device ([type]): [description]
        commands ([type]): [description]

    Returns:
        [type]: [description]
    """
    if "NET_TEXTFSM" not in os.environ:
        os.environ["NET_TEXTFSM"] = "/usr/local/scripts/templates"
    ip = device['ip']
    host = device['host']
    result = {}
    result[host] = {}
    logging.info(start_msg.format(datetime.now().time(), ip))
    with ConnectHandler(**device) as ssh:
        for command, textfsm in commands:
            output = ssh.send_command(command, use_textfsm=textfsm)
            result[host][command] = output
            time.sleep(1)
    logging.info(received_msg.format(datetime.now().time(), ip))
    return result


if __name__ == "__main__":
    print('Script Done!')
