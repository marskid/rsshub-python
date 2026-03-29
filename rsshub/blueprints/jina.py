import os
from flask import Blueprint, render_template, request, Response, current_app
import asyncio
import aiohttp
import requests 
import feedparser
import arrow

from urllib.parse import quote
from rsshub.extensions import cache
from rsshub.async_runner import async_runner
from rsshub.utils import DEFAULT_HEADERS

# Jina API配置
JINA_API_URL = os.getenv('JINA_API_URL')
JINA_API_KEY = os.getenv('JINA_API_KEY')

bp = Blueprint('jina_proxy', __name__, url_prefix='/jina')  

async def jina_proxy(url):
    endpoint = f"{JINA_API_URL}{url}"
    
    headers = {
        "Authorization": f"Bearer {JINA_API_KEY}",
        "X-Return-Format": "html",
        "X-Engine": "direct",
        "X-Base": "final",
        "X-Retain-Images": "none"
    }
    
    async with aiohttp.request(
        method='GET',
        url=endpoint,
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=30)  # 30秒超时
    ) as response:
        return await response.text()

def parse(post):
    base_url = current_app.config['BASE_URL']
    item = {}
    item['title'] = post.title
    item['description'] = post.summary if hasattr(post,'summary') else post.title
    item['pubDate'] = post.published if post.has_key('published') else arrow.now().isoformat()
    item['link'] = f"{base_url}/jina/web?url={quote(post.link if hasattr(post,'link') else '', safe='')}"
    item['author'] = post.author if post.has_key('author') else ''
    return item

@bp.route('/web')
@cache.cached(
    timeout=3600,
    key_prefix=lambda: f"jina_web_{request.args.get('url', '')}")
def web():
    url = request.args.get('url')
    if not url:
        return Response("Error: url parameter is missing or empty", status=400)
    try:
        jina_result = async_runner.run(jina_proxy(url))
        return Response(
            response=jina_result,
            status=200,
        )
    except asyncio.TimeoutError:
        print("Jina API request timed out after 30 seconds")
        return Response(
            response="Jina API request timed out after 30 seconds",
            status=504,
        )

@bp.route('/rss')
def rss():
    feed_url = request.args.get('feed_url')
    if not feed_url:
        return Response("Error: feed_url parameter is missing or empty", status=400)
    res = requests.get(feed_url,headers=DEFAULT_HEADERS,verify=False)
    feed = feedparser.parse(res.text)
    title = feed.feed.title
    description = feed.feed.subtitle if feed.feed.has_key('subtitle') \
        else feed.feed.title
    author = feed.feed.author if feed.feed.has_key('author') \
        else feed.feed.generator if feed.feed.has_key('generator') \
        else title
    posts = feed.entries

    feeds = {
        'title': title,
        'link': feed_url,
        'description': description,
        'author': author,
        'items': list(map(parse, posts)) 
    }
    return render_template('main/atom.xml', **feeds)