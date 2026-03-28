import re
from flask import Response
import requests
from bs4 import BeautifulSoup
import functools
import threading
import hashlib
import pickle
from flask import request
from rsshub.extensions import cache
import arrow
from flask import current_app

# 标题缓存配置
TITLE_CACHE_TIMEOUT = 86400 * 7  # 标题缓存7天
TITLE_CACHE_PREFIX = "title_translation:"

DEFAULT_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

class XMLResponse(Response):
    def __init__(self, response, **kwargs):
        if 'mimetype' not in kwargs and 'contenttype' not in kwargs:
            if response.startswith('<?xml'):
                kwargs['mimetype'] = 'application/xml'
        return super().__init__(response, **kwargs)


def fetch(url: str, headers: dict=DEFAULT_HEADERS, proxies: dict=None):
    try:
        res = requests.get(url, headers=headers, proxies=proxies)
        res.raise_for_status()
    except Exception as e:
        print(f'[Err] {e}')
    else:
        html = res.text
        tree = BeautifulSoup(html, 'html.parser')
        return tree


async def fetch_by_puppeteer(url):
    try:
        from pyppeteer import launch
    except Exception as e:
        print(f'[Err] {e}')
    else:
        browser = await launch(  # 启动浏览器
            {'args': ['--no-sandbox']},
            handleSIGINT=False,
            handleSIGTERM=False,
            handleSIGHUP=False
        )
        page = await browser.newPage()  # 创建新页面
        await page.goto(url)  # 访问网址
        html = await page.content()  # 获取页面内容
        await browser.close()  # 关闭浏览器
        return BeautifulSoup(html, 'html.parser')


def filter_content(items):
    content = []
    p1 = re.compile(r'(.*)(to|will|date|schedule) (.*)results', re.IGNORECASE)
    p2 = re.compile(r'(.*)(schedule|schedules|announce|to) (.*)call', re.IGNORECASE)
    p3 = re.compile(r'(.*)release (.*)date', re.IGNORECASE)

    for item in items:
        title = item['title']
        if p1.match(title) or p2.match(title) or p3.match(title):
            content.append(item)
    return content


def swr_cache(timeout=3600, stale_timeout=86400):
    """
    Stale-While-Revalidate Cache Decorator
    
    Args:
        timeout: 新鲜期（秒），期间内直接返回缓存，不触发刷新
        stale_timeout: 陈腐期（秒），超过新鲜期但在此时间内，返回旧数据并后台刷新
                       同时作为缓存在 Redis 中的最大存活时间
    
    行为：
        - 0 ~ timeout: 直接返回缓存（不刷新）
        - timeout ~ stale_timeout: 返回旧数据 + 后台刷新（60秒内最多一次）
        - > stale_timeout: 缓存失效，同步获取新数据
    
    Example:
        @swr_cache(timeout=300, stale_timeout=3600)  # 5分钟新鲜期，1小时陈腐期
        def get_data():
            return expensive_operation()
    """
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            # 导入 cache 实例（避免循环导入）
            from rsshub.extensions import cache
            
            # 生成唯一的缓存键
            key_data = (f.__name__, args, kwargs, request.path, request.args)
            key_hash = hashlib.md5(pickle.dumps(key_data)).hexdigest()
            cache_key = f"swr_cache:{key_hash}"
            
            # 获取缓存数据
            cached_data = cache.get(cache_key)
            
            # 捕获当前应用和请求信息（用于后台线程）
            app = current_app._get_current_object()
            req_path = request.path
            req_query_string = request.query_string
            
            current_time = arrow.now().timestamp()
            
            if cached_data:
                try:
                    # 解包缓存数据
                    data, timestamp = cached_data
                    age = current_time - timestamp
                    
                    # 情况1：新鲜期内，直接返回（不刷新）
                    if age < timeout:
                        print(f"[SWR] Cache fresh for {req_path}, age: {age:.0f}s")
                        return data
                    
                    # 情况2：陈腐期内，返回旧数据并触发后台刷新
                    elif age < stale_timeout:
                        print(f"[SWR] Cache stale for {req_path}, age: {age:.0f}s, returning stale data")
                        
                        # 使用锁防止重复刷新（60秒内只触发一次）
                        lock_key = f"swr_lock:{key_hash}"
                        if not cache.get(lock_key):
                            print(f"[SWR] Triggering background refresh for {req_path}")
                            cache.set(lock_key, 1, timeout=60)  # 锁60秒
                            threading.Thread(
                                target=refresh_cache,
                                args=(app, req_path, req_query_string, cache_key, f, args, kwargs, stale_timeout),
                                daemon=True
                            ).start()
                        else:
                            print(f"[SWR] Refresh already in progress for {req_path}")
                        
                        return data  # 返回旧数据
                    
                    # 情况3：超过陈腐期，缓存完全失效
                    else:
                        print(f"[SWR] Cache expired for {req_path}, age: {age:.0f}s, fetching fresh data")
                        cache.delete(cache_key)
                        # 继续执行下面的同步获取
                        
                except Exception as e:
                    print(f"[SWR] Error processing cached data for {req_path}: {e}")
                    cache.delete(cache_key)
            
            # 缓存不存在或完全失效，同步获取新数据
            print(f"[SWR] Cache miss for {req_path}, fetching synchronously")
            result = f(*args, **kwargs)
            cache.set(cache_key, (result, current_time), timeout=stale_timeout)
            return result
            
        return decorated_function
    return decorator


def refresh_cache(app, path, query_string, cache_key, func, args, kwargs, stale_timeout):
    """
    后台刷新缓存
    
    Args:
        app: Flask 应用实例
        path: 请求路径
        query_string: 查询字符串
        cache_key: 缓存键
        func: 原函数
        args: 位置参数
        kwargs: 关键字参数
        stale_timeout: 缓存过期时间（秒）
    """
    try:
        print(f"[SWR] Background refreshing {cache_key}")
        
        # 确保 query_string 是字符串
        if isinstance(query_string, bytes):
            query_string = query_string.decode('utf-8')
        
        # 在应用上下文中执行原函数
        with app.test_request_context(path=path, query_string=query_string):
            result = func(*args, **kwargs)
            current_time = arrow.now().timestamp()
            cache.set(cache_key, (result, current_time), timeout=stale_timeout)
            
        print(f"[SWR] Background refresh successful for {cache_key}")
        
    except Exception as e:
        print(f"[SWR] Background refresh failed for {cache_key}: {e}")


def get_title_cache_key(title: str, source: str, target: str) -> str:
    """生成标题缓存键"""
    # 使用 MD5 避免键名过长
    key_data = f"{title}:{source}:{target}"
    key_hash = hashlib.md5(key_data.encode()).hexdigest()
    return f"{TITLE_CACHE_PREFIX}{key_hash}"


def get_cached_title(title: str, source: str, target: str) -> str | None:
    """获取缓存的翻译结果"""
    cache_key = get_title_cache_key(title, source, target)
    cached = cache.get(cache_key)
    if cached:
        # print(f"[Title Cache] Hit: {title[:50]}...")
        return cached
    return None


def set_cached_title(title: str, source: str, target: str, translated: str):
    """缓存翻译结果"""
    cache_key = get_title_cache_key(title, source, target)
    cache.set(cache_key, translated, timeout=TITLE_CACHE_TIMEOUT)
    # print(f"[Title Cache] Set: {title[:50]}...")