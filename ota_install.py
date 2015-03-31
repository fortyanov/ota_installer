# -*- coding: utf-8 -*-
"""
    ota installer

    .. codeauthor:: Fedor Ortyanov <f.ortyanov@roscryptpro.ru>
"""

import getpass
import codecs
import os
import sys
from optparse import OptionParser

__author__ = 'Fedor Ortyanov'
__version__ = '0.1.0'

try:
    from fabric.api import *                                            # пытаемся импортировать необходимые модули из fabric
    from fabric.colors import *
    from fabric.contrib.files import *
    from fabric.contrib.console import confirm                          # необходимо для импользования проверок ввода (альтернатива существующему)
except ImportError as e:                                                # а если не получается, то скачиваем и устанавливаем fabric
    # Install dependencies
    os.system('sudo apt-get install python-pip -y')
    os.system('sudo pip install fabric --timeout=360')                  # и снова импортируем эти модули
    from fabric.api import *
    from fabric.colors import *
    from fabric.contrib.files import *
    from fabric.contrib.console import confirm                          # необходимо для импользования проверок ввода (альтернатива существующему)


def parseOptions(argv):
    usageStr = """USAGE:      python ota_install.py --path <path_to_install> --name <name_of_app> --host <host_string> --user <username>"""
    parser = OptionParser(usageStr)

    parser.add_option('--path', dest='path_to_install',
                      help=u"Укажите путь установки, лучше всего /opt/", default='/opt/')
    parser.add_option('--host', dest='host_string',
                      help=u"Укажите адрес сервера, на котором производить установку, например, 172.20.3.17", default='localhost')
    parser.add_option('--name', dest='name_of_app',
                      help=u"Укажите имя для маршрутизации (не может содержать русские буквы, пробелы и знаки кроме \"-\")\n" +
                           u"Наилучший вариант: ota-<имя_сервера>", default='ota-web')
    parser.add_option('--user', dest='username',
                      help=u"Укажите имя пользователя, от имени которого вы планируете производить установку, \n" +
                           u"он должен обладать правами sudo на сервере, который вы указали.", default=getpass.getuser())

    options, otherjunk = parser.parse_args(argv)
    if len(otherjunk) != 0:
        print 'Use -h for help'
        raise Exception('Command line input not understood: ' + str(otherjunk))

    args = {}
    args['path_to_install'] = options.path_to_install.rstrip('/')
    args['host_string'] = options.host_string
    args['name_of_app'] = options.name_of_app
    args['username'] = options.username
    return args


class OTA(object):
    """
        Собственно класс инсталлятора
    """
    def __init__(self, path_to_install, name_of_app):
        self.path_to_install = path_to_install         # данные которые будут использоваться для настройки чероки
        self.name = name_of_app                          # ########################################################

    def get_config(self, filepath):
        """
            Шаблонизация удаленного файла
        """
        # with cd(CWD):
        content = codecs.open(filepath, 'rb', encoding="utf8").read()                                   # запускаем команду терминала для просмотра содержимого файла и заносим строку с содержимым в content
        content %= self.__dict__                                                                        # подставляем в строку переменные по ключам-атрибутам
        return content                                                                                  # возвращает отформатированную строку

    def install_webserver(self):
        """
            Установка веб-сервера
        """
        env.sudo_user = 'root'
        print(cyan('Install Cherokee'))
        try:
            sudo('apt-get install cherokee -y')                                                               # скачиваем установочник веб-сервера Чероки
        except:
            sudo('add-apt-repository -y ppa:cherokee-webserver')
            sed('/etc/apt/sources.list.d/cherokee-webserver-ppa-trusty.list', 'trusty', 'saucy', use_sudo=True)
            sudo('apt-get update')
            sudo('apt-get install cherokee -y')
        cherokee_conf = self.get_config(os.path.join(CWD, 'ota_install_stuff/cherokee.conf'))                 # адрес файла настроек для Чероки
        append('/etc/cherokee/cherokee.conf', cherokee_conf, use_sudo=True)                                   # заносим в файл отведенный для настроек наши настройки Чероки (дописывает в конец)
        sudo('/etc/init.d/cherokee start')                                                                    # запускаем веб-сервер Чероки


    def make_venv(self):
        """
            Создается хранилище для виртуального окружения в папке с проектом
        """
        sudo('pip install virtualenv')
        with cd(os.path.join(self.path_to_install, 'ota_web')):
            sudo('mkdir venv')
            sudo('virtualenv venv --system-site-package')


    def env_run(self, command, use_sudo=False, env_name="venv", *args, **kwargs):
        """
            Выполнение команды в виртуальном окружении
        """
        env_var = 'source %s && ' % os.path.join(self.path_to_install, 'ota_web', '%s/bin/activate' % env_name)
        if use_sudo:
            if 'user' in kwargs:
                env.sudo_user = kwargs['user']
            else:
                env.sudo_user = 'root'
            return sudo(env_var + command, *args, **kwargs)
        else:
            return run(env_var + command, *args, **kwargs)


    def install_requirements(self):
        """
            Подтягиваем pip-ом сорцы из requirements.txt содержащемся в проекте ота_web
        """
        with cd(os.path.join(self.path_to_install, 'ota_web')):
            self.env_run(command='pip install -r requirements.txt', use_sudo=True)

    def deploy_ota(self):
        """
            Развертывание ота на сервере из архива (архив создавался из клонированной гитом версии)
        """
        put(os.path.join(CWD, 'ota_web'), self.path_to_install, use_sudo=True)         # заливаем на сервак папку с проектом ОТА
        sudo('rm -rf %s' % os.path.join(self.path_to_install, 'ota_web', '.git'))
        sudo('rm %s' % os.path.join(self.path_to_install, 'ota_web', 'otaBD.db'))      # если есть файл БД то удаляем (сделаем свой с блекджеком и таблицами)

        self.install_requirements()
        self.env_run(command='python %s/ota_web/manage.py syncdb --noinput' % self.path_to_install, use_sudo=True)   # инициируем создание БД и заливаем туда fixtures (noinput значит без создания суперюзера)
        sudo('chown %s %s' % (env.user, os.path.join(self.path_to_install, 'ota_web', 'otaBD.db')))                  # даем права на доступ к файлу базы для пользователя от имени которого будет импользоваться приложение (от его же имени происходит установка)
        sudo('chown %s %s' % (env.user, os.path.join(self.path_to_install, 'ota_web')))                              # оказывается недостаточно дать права файлу, необходимо дать их также и объемлющей его дирректории

        with cd(os.path.join(self.path_to_install, 'ota_web')):
            sudo("mkdir logs")                                                      # сюда чероки будет скидывать логи
            sudo("chmod 777 logs")

    def clean_server(self):
        """
            Очистка сервера от приложения ОТА
        """
        sed(filename='/etc/cherokee/cherokee.conf', before='# Gen for ota".*"interpreter', after='', use_sudo=True)           # очищаем чероки от настроек ота TODO не работает, надо доделать
        sudo('rm -rf %s' % os.path.join(self.path_to_install, 'ota_web'))                                                     # удаляем сам проект с сервера










if __name__ == "__main__":
    CWD = os.path.abspath(os.path.split(sys.argv[0])[0])
    print('CWD: %s' % CWD)
    args = parseOptions(sys.argv[1:])
    ota = OTA(path_to_install=args['path_to_install'], name_of_app=args['name_of_app'])

    env.host_string = '%s@%s' % (args['username'], args['host_string'])
    env.user = args['username']
    env.password = prompt('password: ')
    env.sudo_user = 'root'

    with settings(host_string=env.host_string):
        append('/etc/hosts', '127.0.0.1 %s' % ota.name, use_sudo=True)
        ota.clean_server()
        ota.install_webserver()
        sudo('mkdir %s' % os.path.join(ota.path_to_install, 'ota_web'))
        ota.make_venv()
        ota.deploy_ota()
        sudo('/etc/init.d/cherokee restart')                   # перезапуск Чероки на всякий

























