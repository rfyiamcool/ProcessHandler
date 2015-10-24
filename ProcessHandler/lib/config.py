#encoding=utf-8

import os
from ConfigParser import SafeConfigParser, NoOptionError

from ProcessHandler.lib.singleton import Singleton

class Config(object):
    """use singleton avoid global variables"""
    __metaclass__ = Singleton

    DEFAULT_CONFIG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../conf/config.ini'))
    ACTUAL_CONFIG_FILE = None
    SECTION_NAME = 'main'
    def __init__(self):
        self.load_config()

    def load_config(self):
        config_file = self.__class__.ACTUAL_CONFIG_FILE or self.__class__.DEFAULT_CONFIG_FILE
        self._cfg = SafeConfigParser()
        self._cfg.read([config_file, ])

    def get(self, option, section=None, value_type=str):
        return self._cfg._get(section or self.__class__.SECTION_NAME, value_type, option)

    def __getattr__(self, option):
        try:
            return self.get(option)
        except NoOptionError as e:
            return None

if __name__ == '__main__':
    #Config.SECTION_NAME = 'ssss'
    #print Config.SECTION_NAME
    print Config().get('base_path')
