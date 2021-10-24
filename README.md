# Networks Management
## _Скрипты по работе с сетевым оборудованием_

[![Build Status](https://travis-ci.org/joemccann/dillinger.svg?branch=master)](https://travis-ci.org/joemccann/dillinger)

## Возможности

- Инвентаризация коммутаторов
- Инвентаризация Wi-Fi точек доступа
- Актуализация информации в учётных системах JIRA CMDB. 


## Технологии

В процессе разработки использовались следующие инструменты:

- [Python] - Язык разработки.
- [Visual Studio Code] - IDE
- [GitLab] - Git сервер.
- [NetMiko] - Модуль python для работы SSH.
- [JIRA Insight] - Модуль для работы с JIRA
- [discovernetmiko] - Модуль для составления словарей необходимые для подключения к устройствам по SSH.

## Установка

Требуется [Python] 3.8.5+ для работы.
Для установки сделайте клонирование репозитория.
Для примера:

```sh
cd /usr/local/scripts


```

Установите зависимости.

```sh
pip install -r requirements.txt 
```

Установите сам пакет

```sh
pip install .
```

## Как использовать

 Укажите в config.ini:
```
    - login = "_Логин для доступа по SSH на оборудование_"
    - password = "пароль от логина выше"
    - network = "IP-диапазон в котором будет производиться сбор информации"
    - Для работы с JIRA CMDB смотри информацию по модулю 
```
Или используйте их сразу при передаче значений. 
Рекомендуется использовать ConfigParser

Создайте объекты подключения к серверу JIRA, как сказано в документации к модулю [JIRA Insight].

## Логика работы скриптов update_cmdb*

- Производиться поиск словарей поключений. Который в системе сделан в JSON формате.
- В случае его отсутствия запускает модуль [discovernetmiko]
- Производиться опрос информации.
- Её обработка 
- Передача в CMDB

```python
    jira = Insight(jira_url, login, password)
    schema = InsightSchema(jira, schema_name)
    schema_obj_type = schema.get_object_type(object_type_name)
```


## Автор

Кокорников Илья 



[//]: # (These are reference links used in the body of this note and get stripped out when the markdown processor does its job. There is no need to format nicely because it shouldn't be seen. Thanks SO - http://stackoverflow.com/questions/4823468/store-comments-in-markdown-syntax)


   [Python]: <https://www.python.org>
   [Visual Studio Code]: <https://code.visualstudio.com/>
   [GitLab]: <https://gitlab.com/gitlab-org>
   [discovernetmiko]: <https://gitlab.kalashnikovconcern.ru/kovo/get_netdevices_project>
   [JIRA Insight]: <https://gitlab.kalashnikovconcern.ru/kovo/jirainsight_project>
   [NetMiko]: <https://github.com/ktbyers/netmiko>
