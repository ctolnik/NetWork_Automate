import configparser
import logging

import jirainsight
from jira import JIRA

CONFIGFILE = '/usr/local/scripts/configs/config_cmdb.ini'
CMDB_OBJECT_TYPE_NAME = 'Virtual Machine[x]'

# Константы по JIRA
JQL = 'project = RFC AND issuetype = "Создание сервера" AND "DNS имя" ~ "{dns_name}"'
PROJECT_NAME = 'IN'
SUBJECT_ISSUE = 'Отсутствут RFC VM - {name}'
DESCRIPTION_ISSUE = 'Укажите основного и замещающего администратора у объекта {url}'
TYPE_ISSUE = 'Задача'
ASSIGN_ISSUE = 'kovo'


def get_objects_empty_attribute(object_type, attribute):
    result = {}
    for id, schema_object in object_type.objects.items():
        if schema_object.attributes[attribute].value is None:
            if schema_object.attributes['Deleted'].value is False:
                result[id] = schema_object
    return result


def search_issue(dns_name):
    result = None
    try:
        result = jira.search_issues(JQL.format(dns_name=dns_name))
    except Exception:
        logging.warning(f"Ошибка поиска запроса для - {dns_name}")
    if result:
        return result[0]


def get_vm_attributes(key):
    issue = jira.issue(key)
    first_admin = issue.fields.customfield_20515
    other_admin = issue.fields.customfield_16231
    other_admin = [i.name for i in other_admin]
    return {
        'First Administrator': first_admin.name,
        'Other Administrators': other_admin
    }


def check_jira_issues(object):
    for issue in object.JIRA_issues['jiraIssues']:
        issue = jira.issue(issue['jiraIssueKey'])
        summary = issue.fields.summary
        if summary == SUBJECT_ISSUE.format(name=object.name):
            return True
    return False


def main():
    logging.info("Получаем список некоректных объектов из CMDB")
    wrong_objects = get_objects_empty_attribute(
        schema_obj_type, 'First Administrator')
    logging.info(f"В CMDB найдено: {len(wrong_objects)} некоректных объектов")

    no_rfc = []
    logging.info(f"Начинаем перебор объектов из CMDB")
    for id, object in wrong_objects.items():
        dns_name = object.attributes['DNS Name'].value
        issue = search_issue(dns_name)
        if issue is not None:
            logging.info(f"Найден {issue.key} для - {object.name}")
            attributes = get_vm_attributes(issue.key)
            logging.info("Обновляем атрибуты в CMDB")
            for attribute, value in attributes.items():
                attr_id = object.attributes[attribute].id
                object.update_object({attr_id: value})
            rfc_id = object.attributes['Request number'].id
            status = object.update_object({rfc_id: issue.key})
            logging.info(
                f"CMDB объект: {object.name} обновлен: {status['updated']}"
            )
        else:
            logging.info(f"RFC для {object.name} - не найден")
            jira_issues = object.get_jira_issues()
            if len(object.JIRA_issues['jiraIssues']) > 0:
                if check_jira_issues(object):
                    logging.info(
                        f"Задача для {object.name} существует. Пропуск")
                    continue
            obj_url = (
                schema_obj_type._objects[id].object_json['_links']['self'])
            issue_dict = {
                'project': {'id': project.id},
                'summary': SUBJECT_ISSUE.format(name=object.name),
                'description': DESCRIPTION_ISSUE.format(url=obj_url),
                'issuetype': {'name': TYPE_ISSUE},
                'assignee': {'name': ASSIGN_ISSUE},
                'customfield_16250': [
                    {'key': object.object_json['objectKey']}
                ],
            }
            no_rfc.append(issue_dict)
        logging.info(f"Обработка {object.name} завершена")

    logging.info(f"Создаём: {len(no_rfc)} задач в JIRA ")
    issues = jira.create_issues(field_list=no_rfc)


if __name__ == '__main__':
    # Настраиваем логирование
    logging.basicConfig(
        format='%(threadName)s %(name)s %(levelname)s: %(message)s',
        level=logging.INFO)

    # Парсим конфиг файл.
    config = configparser.ConfigParser()
    config.read(CONFIGFILE)
    login = config.get('jira', 'login', fallback='not exists')
    password = config.get('jira', 'password', fallback='not exists')
    url = config.get('jira', 'url', fallback='https://z')
    schema_name = config.get('jira', 'schema_name', fallback='CMDB')

    logging.info("Подключаемся CMDB и JIRA")
    jira_options = {'server': url}
    jira = JIRA(options=jira_options, basic_auth=(login, password))
    project = jira.project(PROJECT_NAME)
    insight = jirainsight.Insight(url, login, password)
    schema = jirainsight.InsightSchema(insight, schema_name)
    schema_obj_type = schema.get_object_type(CMDB_OBJECT_TYPE_NAME)
    main()
    logging.info(f"Работа скрипта завершена")
