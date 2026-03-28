import os
import sys


basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


class BaseConfig:
    SITE_NAME = 'RSSHub'
    GITHUB_USERNAME = ''
    EMAIL = ''
    BASE_URL = os.environ.get('BASE_URL') or 'http://127.0.0.1:5000'
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'fga43534gsd5'
    DEBUG_TB_INTERCEPT_REDIRECTS = False


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    ENV = 'development'


class TestingConfig(BaseConfig):
    TESTING = True


class ProductionConfig(BaseConfig):
    DEBUG = False
    ENV = 'production'


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig
}