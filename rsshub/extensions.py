from flask_bootstrap import Bootstrap
from flask_moment import Moment
from flask_caching import Cache
import os


bootstrap = Bootstrap()
moment = Moment()

# 仅在开发环境中导入和初始化 debugtoolbar
debugtoolbar = None
if os.environ.get('FLASK_ENV') == 'development':
    try:
        from flask_debugtoolbar import DebugToolbarExtension
        debugtoolbar = DebugToolbarExtension()
    except ImportError:
        pass  # 开发环境缺失时忽略，避免阻断启动

# 基础缓存配置
cache_config = {
    "DEBUG": True,
    "CACHE_DEFAULT_TIMEOUT": 3600,
}

# 根据环境设置缓存类型
if os.environ.get('FLASK_ENV') == 'development':
    cache_config["CACHE_TYPE"] = "simple"  # 开发环境使用内存缓存
else:
    cache_config.update({
        "CACHE_TYPE": "redis",
        "CACHE_REDIS_HOST": os.environ.get('REDIS_HOST', '127.0.0.1'),
        "CACHE_REDIS_PORT": int(os.environ.get('REDIS_PORT', 6379)),
        "CACHE_REDIS_PASSWORD": os.environ.get('REDIS_PASSWORD', ''),
        "CACHE_REDIS_DB": int(os.environ.get('REDIS_DB', 0)),
        "CACHE_KEY_PREFIX": os.environ.get('CACHE_KEY_PREFIX', 'rsshub_'),
        "CACHE_OPTIONS": {
            "socket_connect_timeout": 5,
            "socket_timeout": 5,
            "retry_on_timeout": True,
            "max_connections": 10,
        }
    })

cache = Cache(config=cache_config)