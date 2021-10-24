#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
import logging
import os
from configparser import ConfigParser

import psycopg2
from get_netdevices import build_device_list
from send_commands import send_command_parallel

# Настройки логирования
logging.basicConfig(
    format='%(threadName)s %(name)s %(levelname)s: %(message)s',
    level=logging.INFO)

# Путь к конфигу
CONFIGFILE = 'config.ini'
# Парсим конфигурационный файл
config = ConfigParser()
config.read(CONFIGFILE)
netLogin = config.get('net', 'netLogin', fallback='not exists')
netPassword = config.get('net', 'netPassword', fallback='not exists')
network = config.get('net', 'network', fallback='not exists')
threads = int(config.get('net', 'threads', fallback='not exists'))
dbUser = config.get('db', 'user', fallback='not exists')
dbPassword = config.get('db', 'password', fallback='not exists')
dbName = config.get('db', 'db_name', fallback='not exists')
dbHost = config.get('db', 'host', fallback='not exists')
# Сбор переменных в одну
database = {
    "dbname": dbName,
    "host": dbHost,
    "user": dbUser,
    "password": dbPassword
}

netinfo = {
    "ip_net": network,
    "netLogin": netLogin,
    "netPassword": netPassword,
    "threads": threads
}


def get_mac_info(devices):
    """Получение по SSH в мультипотоке вывод mac-address table

    Args:
        devices (list): список словарей устройств  для подключений

    Returns:
        list: Возвращает список с данными по команде show. 
    """
    logging.info("*"*60)
    logging.info("Получение mac-address table")
    logging.info("*"*60)
    result = []
    device_types = set([i['device_type'] for i in devices])
    for type in device_types:
        list_type = [i for i in devices if i["device_type"] == type]
        # TODO: Вынести какая команда для устройства в отдельный словарь.
        # TODO: Или перевод на ООП и метод будет определять команду.
        if type == "cisco_ios" or type == "cisco_s300":
            command = "show mac address-table"
        else:
            command = "show mac-address"
        logging.info(f"Опрос {type}, командой {command}")
        result += send_command_parallel(list_type, command)
        logging.info(f"Опрос {type} завершён")
    logging.info("*"*60)
    logging.info("Сбор информации о mac адресах завершён")
    logging.info("*"*60)
    return result


def parse_mac_info(raw_data):
    """Обработка вывода show mac address. Исключение транковых портов.
    Для 

    Args:
        raw_data (list): вывод функции по сбору данных по SSH

    Returns:
        list: Список кортежей для передачи в БД.
    """
    logging.info("*"*60)
    logging.info("Обработка данных для передачи в СУБД")
    logging.info("*"*60)
    lists = []
    for raw in raw_data:
        for host, output in raw.items():
            try:
                raw_ports = [i['port'] for i in output]
                all_ports = set([i['port'] for i in output])
            # Получаям порты, где не более 2ух мак-адресов
                access_ports = [
                    u_port for u_port in all_ports if raw_ports.count(u_port) < 2]
                macs = [(host, i['destination_address'], i['port'], i['vlan'])
                        for i in output if i['port'] in access_ports]
                lists.append(macs)

            except:
                print('Проблема с обработкой')
    # Объединяем списки и сортируем
    result = list(set().union(*lists))
    result.sort()
    logging.info("*"*60)
    logging.info("Обработка завершена")
    logging.info("*"*60)
    return result


def insert_switches(db, data):
    sql = """INSERT INTO switches VALUES(%s, %s, %s)
            ON CONFLICT ON CONSTRAINT pk_switch_switch_hostname DO NOTHING;"""
    connection = None
    try:
        connection = psycopg2.connect(**db)
        cursor = connection.cursor()
        cursor.executemany(sql, data)
        connection.commit()
        logging.info("Record inserted successfully")
    except (Exception, psycopg2.Error) as error:
        logging.error("Error while connecting to PostgreSQL", error)
    finally:
        if connection:
            cursor.close()
            connection.close()
            logging.info("PostgreSQL connection is closed")


def insert_mac_info(db, data):
    sql = "INSERT INTO mac_addresses(switch_hostname, mac_address, switch_port, switch_vlan) VALUES(%s, %s, %s, %s)"
    connection = None
    try:
        connection = psycopg2.connect(**db)
        cursor = connection.cursor()
        cursor.executemany(sql, data)
        connection.commit()
        logging.info("Record inserted successfully")
    except (Exception, psycopg2.Error) as error:
        logging.error("Error while connecting to PostgreSQL", error)
    finally:
        if connection:
            cursor.close()
            connection.close()
            logging.info("PostgreSQL connection is closed")


if __name__ == "__main__":
    logging.info("*"*60)
    logging.info("Script Begin")
    logging.info("*"*60)
    filedump = "/usr/local/scripts/output/x_switches.json"
    if os.path.isfile(filedump):
        with open(filedump) as f:
            x_switches = json.load(f)
    else:
        # x_switches = generate_list_connet(**netinfo)
        x_switches = build_device_list(
            network, netLogin, netPassword, filedump)
    # Структура данных для передачи в СУБД по заполнению таблицы с коммутаторами.
    # TODO: Проверить на отсутствие создания дублирующих коммутаторов
    list2db = [(i['host'], i['ip'], i['device_type'].split('_')[0])
               for i in x_switches]

    # Внесение информации по коммутаторам в СУБД. В таблицу switches.
    insert_switches(database, list2db)

    # Получение по NetMiko вывод команды show mac-address table. С обработкой TextFSM.
    raw_mac_info = get_mac_info(x_switches)
    # Обработка полученного вывода для передачи в СУБД
    x_mac_info = parse_mac_info(raw_mac_info)
    # Внесение информации по мак-адресам в СУБД
    insert_mac_info(database, x_mac_info)
    logging.info("*"*60)
    logging.info("Script Complete")
    logging.info("*"*60)
