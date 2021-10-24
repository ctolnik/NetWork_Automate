import logging
import os
import random
from configparser import ConfigParser
from datetime import datetime

import jirainsight
import ldap3
import psycopg2
import requests
from jinja2 import Environment, FileSystemLoader

CONFIGFILE = 'config.ini'
DATE_FORMAT = '%d.%m.%y %H:%M'
DATE_BLANK = datetime(2000, 1, 1)
ALPHABET = (
    '0123456789'
    'abcdefghijklmnopqrstuvwxyz'
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    '!@#$%^&*()_+'
)
ENV = Environment(loader=FileSystemLoader("."), trim_blocks=True)
TEMPLATE = ENV.get_template("cfg_template.txt")
EXT_N = 'Cell'
CONTEXT = {
    'Корпоративные': 'level-0',
    'Мобильные': 'level-1',
    'Междугородние': 'level-2',
    'Международные': 'level-3'
}

config = ConfigParser()
config.read(CONFIGFILE)
ad_login = config.get('ldap', 'ldapLogin', fallback='not exists')
ad_password = config.get('ldap', 'ldapPassword', fallback='not exists')
dc_server = config.get('ldap', 'ldapserver', fallback='not exists')
ldap_base = config.get('ldap', 'ldapBase', fallback='not exists')
domain = config.get('ldap', 'domain', fallback='not exists')
ntp_server1 = config.get('ldap', 'ntp_server1', fallback='not exists')
ntp_server2 = config.get('ldap', 'ntp_server2', fallback='not exists')
jira_url = config.get('cmdb', 'cmdbURL', fallback='not exists')
cmdb_login = config.get('cmdb', 'cmdbLogin', fallback='not exists')
cmdb_password = config.get('cmdb', 'cmdbPassword', fallback='not exists')
cmdb = config.get('cmdb', 'cmdbSchemaName', fallback='CMDB')
cmdb_ip_phones = config.get(
    'cmdb', 'cmdbObjectTypeName1', fallback='not exists')
cmdb_ip_extensions = config.get(
    'cmdb', 'cmdbObjectTypeName2', fallback='not exists')
path_conf_phone = config.get('general', 'pathConfPhone', fallback='not exists')
var_number = config.get('general', 'var_number', fallback='not exists')
var_name = config.get('general', 'var_name', fallback='not exists')
var_tz = config.get('general', 'var_tz', fallback='not exists')
tz = config.get('general', 'tz', fallback='not exists')
var_ntp1 = config.get('general', 'var_ntp1', fallback='not exists')
var_ntp2 = config.get('general', 'var_ntp2', fallback='not exists')
var_password = config.get('general', 'var_password', fallback='not exists')
var_password = config.get('general', 'var_password', fallback='not exists')
db_user = config.get('db', 'user', fallback='not exists')
db_password = config.get('db', 'password', fallback='not exists')
db_name = config.get('db', 'db_name', fallback='not exists')
db_host = config.get('db', 'host', fallback='not exists')
db_port = config.get('db', 'port', fallback='not exists')
ip_login = config.get('phone', 'ip_login', fallback='not exists')
ip_password = config.get('phone', 'ip_password', fallback='not exists')

logging.basicConfig(
    format='%(threadName)s %(name)s %(levelname)s: %(message)s',
    level=logging.INFO)


def get_date_file(path, file):
    modify_date = DATE_BLANK
    if os.path.exists(path+"/"+file):
        modify_date = datetime.fromtimestamp(os.path.getmtime(path+"/"+file))
        logging.info(
            f"Время модификации: {modify_date} "
            f" файла конфигурации:{file}"
        )
        return modify_date
    logging.warning(f"Файл конфигурации {file} отсутствует")
    return modify_date


def password_generator(length):
    result = ''
    for i in range(length):
        symbol = random.choice(ALPHABET)
        result += symbol
    return result


def search_ad_attributes(
    server, login, password, base, attr_name, attr_value,
    obj_cls='Person', enabled_only=False, property=['cn']
):
    ad_server = ldap3.Server(server, get_info=ldap3.ALL)
    conn = ldap3.Connection(
        ad_server, login, password, auto_bind=True
    )
    if enabled_only:
        search_request = (
            f'(&(objectCategory={obj_cls})'
            f'(!(UserAccountControl:1.2.840.113556.1.4.803:=2))'
            f'({attr_name}={attr_value}))'
        )
    else:
        search_request = f'(&(objectCategory={obj_cls})({attr_name}={attr_value}))'
    if conn.search(base, search_request, ldap3.SUBTREE, attributes=property):
        return conn.entries


def set_ad_attribute(
        server, login, password, dn, attr_name, attr_value=[''],):
    ad_server = ldap3.Server(server, get_info=ldap3.ALL)
    conn = ldap3.Connection(
        ad_server, login, password, auto_bind=True
    )
    conn.modify(
        dn, {attr_name: [(ldap3.MODIFY_REPLACE, [attr_value])]}
    )
    if conn.result['description'] == 'success':
        logging.info(
            f'Значение атрибута {attr_name} успешно изменено на {attr_value}'
        )

        return 'success'
    logging.error(
        f"Не удалось изменить {attr_name} на {attr_value} для {dn}")


def get_AD_FIO_by_phone(phone_number):
    result = search_ad_attributes(
        dc_server, ad_login, ad_password, ldap_base,
        'telephoneNumber', phone_number
    )
    if len(result) == 1:
        result = result[0].cn[0].split()
        result = f"{result[0]} {result[1][0]}. {result[2][0]}."
        return result


def check_ADuser(login):
    """Проверяет блокировку уз и номер телефона

    Args:
        login (str): Логин пользователя в AD

    Returns:
        [list]: Номере телефона и код состояния
    """
    result = search_ad_attributes(
        dc_server, ad_login, ad_password, ldap_base,
        'sAMAccountName', login,
        property=['UserAccountControl', 'telephoneNumber', 'cn']
    )
    if result is not None:
        if len(result) == 1:
            phone = result[0].telephoneNumber.value
            status = result[0].userAccountControl.value
            label = result[0].cn.value.split()
            if len(label) == 3:
                label = f"{label[0]} {label[1][0]}. {label[2][0]}."
            elif len(label) == 1:
                label = label[0]
            else:
                label = f"{label[0]} {label[1][:2]}."
            return [phone, status, label]
    logging.error(f"Поиск - {login} в AD вернул пустой результат")


def check_AD_phone(login, phone_cmdb):
    result = search_ad_attributes(
        dc_server, ad_login, ad_password, ldap_base,
        'sAMAccountName', login,
        property=['cn', 'telephoneNumber']
    )
    if len(result) == 1:
        phone_ad = result[0].telephoneNumber.value
        if phone_ad is None:
            phone_ad = 0
        else:
            phone_ad = int(phone_ad)
        if phone_ad != phone_cmdb:
            logging.warning(f"В AD {phone_ad} исправляем на {phone_cmdb}")
            return set_ad_attribute(
                dc_server, ad_login, ad_password, result[0].entry_dn,
                'telephoneNumber', phone_cmdb
            )


def check_update_status(insight_object, config):
    config_date = get_date_file(path_conf_phone, config)
    cmdb_date = insight_object.attributes['Updated'].value
    logging.info("Получаем информацию по конфигурации")
    cmdb_date = datetime.strptime(cmdb_date, DATE_FORMAT)
    compare_dates = config_date > cmdb_date
    if compare_dates:
        logging.info(
            "Не требуется обновления конфигурационного файла. Пропускаем устройство")
        return False
    else:
        logging.info("Конфиг файл необходимо актуализировать.")
        insight_object.reboot = False
        if config_date != DATE_BLANK:
            insight_object._provision = True
        return True


def generate_ext_config(obj_attrs):
    cells = {}
    for attribute, values in obj_attrs.items():
        if attribute.startswith(EXT_N):
            if values.value is not None:
                id = values.name.replace(EXT_N, '')
                number = values.value
                label = get_AD_FIO_by_phone(number)
                cells[id] = [number, label]
    return cells


def generate_phone_config(insight_object, panels=None):
    obj = insight_object.attributes
    result = {}
    result[var_number] = obj['Phone Number'].value
    result[var_name] = obj['Name'].value
    result[var_password] = password_generator(16)
    insight_object._password = result[var_password]
    result[var_ntp1] = ntp_server1
    result[var_ntp2] = ntp_server2
    result[var_tz] = tz
    # result[var_manager_ip] = manager_ip
    cells = generate_ext_config(obj)
    if panels:
        for panel in panels:
            extensions = generate_ext_config(panel.attributes)
            cells.update(extensions)
    if cells:
        result[EXT_N] = cells
    return TEMPLATE.render(result)


def query_db(query):
    result = None
    conn = None
    try:
        conn = psycopg2.connect(dbname=db_name, user=db_user,
                                password=db_password, host=db_host)

        cur = conn.cursor()
        cur.execute(query)
        result = cur.fetchall()

    except (Exception, psycopg2.DatabaseError) as error:
        logging.error(error)
    finally:
        if conn:
            cur.close()
            conn.close()
            logging.info("Соединение с PostgreSQL закрыто")
        return result


def insert_db(query):
    result = None
    conn = None
    try:
        conn = psycopg2.connect(dbname=db_name, user=db_user,
                                password=db_password, host=db_host)
        cur = conn.cursor()
        cur.execute(query)
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        logging.error(error)
    finally:
        if conn is not None:
            conn.close()
    logging.info("Соединение с PostgreSQL закрыто")


def update_db(query):
    result = None
    conn = None
    try:
        conn = psycopg2.connect(dbname=db_name, user=db_user,
                                password=db_password, host=db_host)
        cur = conn.cursor()
        cur.execute(query)
        conn.commit()
        count = cur.rowcount
        cur.close()
        logging.info(f"Успешно обновлено записей: {count}")
    except (Exception, psycopg2.DatabaseError) as error:
        logging.error(error)
    finally:
        if conn is not None:
            conn.close()
    logging.info("Соединение с PostgreSQL закрыто")


def processing_db(object):
    mac_address = object.attributes['MAC-address'].value
    caller_id = object.attributes['Phone Number'].value
    context = object.attributes['Call Rights'].value[0]
    context = CONTEXT[context]

    GET_MAC = f"SELECT account FROM macs WHERE mac = '{mac_address}'"
    GET_CONTEXT = (
        "SELECT context FROM ps_endpoints "
        f"WHERE id = '{caller_id}'"
    )
    GET_PEER = ("SELECT context, callerid "
                f"FROM ps_endpoints WHERE auth = 'auth{caller_id}'"
                )
    ADD_MAC = (
        "INSERT INTO macs (mac, account) "
        f"VALUES('{mac_address}', '{caller_id}')"
    )
    UPDATE_MAC = (
        "UPDATE macs SET account = "
        f"{caller_id} WHERE mac = '{mac_address}'"
    )
    CHG_PASS = (
        "UPDATE ps_auths set password = '{password}' "
        "WHERE username = '{db_caller_id}'"
    )
    CHG_CONTEXT = (
        f"UPDATE ps_endpoints set context = '{context}' "
        f"WHERE id = '{caller_id}'")

    ADD_AORS = (
        "INSERT INTO ps_aors (id, max_contacts, qualify_frequency, "
        "qualify_timeout,remove_existing) "
        f"VALUES ({caller_id}, 1, 300, 10.0, 'yes');"
    )
    ADD_AUTH = (
        "INSERT INTO ps_auths (id, auth_type, password, username) "
        f"VALUES ('auth{caller_id}, 'userpass', "
        "'{password}', "
        f"'{caller_id}')"
    )
    ADD_EP = (
        "INSERT INTO ps_endpoints (id, transport, aors, "
        "auth, context, disallow, allow, direct_media, dtmf_mode, "
        "send_diversion, send_pai, callerid, trust_id_inbound, "
        "trust_id_outbound, use_avpf, device_state_busy_at,language, "
        "allow_transfer, allow_subscribe, sdp_owner, sdp_session, "
        "rtp_timeout, acl) "
        f"VALUES ('{caller_id}', 'udp-transport', '{caller_id}', "
        f"'auth{caller_id}', '{context}', 'all', 'alaw', 'no', "
        "'rfc4733', 'yes', 'yes', '{label}', 'no', 'yes', "
        "'no', 2, 'ru', 'yes', 'no', 'PBXxO', 'PBXxS', "
        "120, 'acl_def_phone)"
    )

    logging.info(f"Проверяем соответствие mac - номер в БД")

    mac_record = query_db(GET_MAC)
    if mac_record:
        db_caller_id = int(mac_record[0][0])
        logging.info(
            "Номер закрепленый в БД за мак адресом "
            f"{mac_address}: {db_caller_id}"
        )
        if db_caller_id != caller_id:
            update_db(UPDATE_MAC)
            # update_db(CHG_PASS.format(db_caller_id=db_caller_id, password=object._password))
            update_db(CHG_CONTEXT)

    else:
        logging.warning(
            f"Отсутствует запись в таблице с маками для mac {mac_address}"
        )
        if caller_id:
            logging.info("Добавляю запись в таблицу с маками")
            add_mac = insert_db(ADD_MAC)
        else:
            logging.error("Не получен caller id из CMDB")

    logging.info(f"Проверяем контекст")
    context_record = query_db(GET_CONTEXT)
    if context_record:
        db_context = context_record[0][0]
        logging.info(
            "Контекст в БД у номера "
            f"{caller_id}: {db_context}"
        )
        if db_context != context:
            logging.info(f"Меняем контекст на {context}")
            update_db(CHG_CONTEXT)

    logging.info(f"Проверяем peer")
    peer_record = query_db(GET_PEER)
    if peer_record:
        db_caller = peer_record[0][1]
        logging.info(
            "В БД метка у номера "
            f"{caller_id}: {db_caller}"
        )
        if db_context != context:
            logging.info(f"Меняем контекст на {context}")
            update_db(CHG_CONTEXT)
    else:
        logging.warning(
            f"Не найдена запись в таблице для номера {caller_id}"
        )
        logging.info(
            f"Вставляю новую запись в БД для {caller_id}"
        )
        label = object._label
        label = f"{label}<{caller_id}>"
        insert_db(ADD_AORS)
        insert_db(ADD_AUTH)
        insert_db(ADD_EP.format(label=label, password=object._password))
    logging.info('Проверка по СУБД завершена')


def auto_provision_conf(obj):
    host = obj._dns_name
    url = f"http://{ip_login}:{ip_password}@{host}/cgi-bin/ConfigManApp.com?key=AutoP"
    request = requests.get(url)
    request.raise_for_status()
    return request


def main():
    logging.info("Устанавливаем подключение к CMDB.")
    jira = jirainsight.Insight(jira_url, cmdb_login, cmdb_password)
    schema = jirainsight.InsightSchema(jira, cmdb)
    cmdb_phones = schema.get_object_type(cmdb_ip_phones)
    cmdb_ext_panels = schema.get_object_type(cmdb_ip_extensions)
    logging.info("Перебор объектов в CMDB.")
    for phone in cmdb_phones.objects.values():
        logging.info(f"Проверка {phone.name}")
        ext_panels = []
        phone_update = False
        panel_update = False
        phone._provision = False
        own = phone.attributes['Owner'].values_json[0]['user']['name']
        logging.info("Перебор объектов в CMDB.")
        status = check_ADuser(own)
        phone._label = status[2]
        if status[1] == 514:
            logging.warning(f"Пользователь {own} отключен")
        else:
            logging.info(f"Пользователь {own} активный")
            check_AD_phone(own, phone.attributes['Phone Number'].value)
        config_filename = f"{phone.attributes['MAC-address'].value}.ini"

        if len(phone.attributes['Extension Panel'].values_json) > 0:
            panels = phone.attributes['Extension Panel'].values_json
            for panel in panels:
                logging.info(
                    f"Подключена панель расширения {panel['displayValue']}"
                )
                panel_id = panel['referencedObject']['id']
                insight_object = cmdb_ext_panels.objects[panel_id]
                panel_update = check_update_status(
                    insight_object,
                    config_filename
                )
                ext_panels.append(insight_object)

        phone_update = check_update_status(phone, config_filename)
        if any([phone_update, panel_update]):
            configa = generate_phone_config(phone, panels=ext_panels)
            with open(path_conf_phone+"/"+config_filename, 'w') as f:
                f.write(configa)
            logging.info(f"Конфигурация сохранена в файл: {config_filename}.")
            dbupdate = update_db(phone)
            logging.info(f"Обновление БД завершено.")
        if phone._provision:
            logging.info(f"Телефон будет обновлен.")
            phone._dns_name = f"{phone.name}.{domain}"
            provision = auto_provision_conf(phone)

        processing_db(phone)
    logging.info("Синхронизация завершена.")
    logging.info("Скрипт завершён.")


if __name__ == '__main__':

    main()

    print('Done')
