# newsnow_ai.py
import re
import asyncio
import arrow
from bs4 import BeautifulSoup
from urllib.parse import urljoin

try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


async def get_ai_news():
    """使用 Playwright 获取 NewsNow AI 新闻"""
    async with async_playwright() as p:
        async with await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        ) as browser:
            page = await browser.new_page()
            
            # 反检测设置
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            await page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })

            # 拦截不必要的资源
            await page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,css}", 
                           lambda route: route.abort())
            
            url = "https://www.newsnow.co.uk/h/Science/AI"
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            
            # 等待文章加载
            try:
                await page.wait_for_selector('.article', timeout=10000)
            except:
                pass  # 超时也继续
            
            # 滚动加载更多内容
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(1.5)
            
            content = await page.content()
            await browser.close()
            
            soup = BeautifulSoup(content, 'html.parser')
            
            all_articles = []
            title = 'NewsNow - Artificial Intelligence (AI) News'
            description = 'Latest AI news aggregated from global sources'
            
            # 提取 Top News
            top_articles = soup.select('.newsfeed__articles--top .article')
            for article in top_articles[:20]:
                card = article.select_one('.article-card')
                if not card:
                    continue
                
                # 标题和链接
                title_elem = card.select_one('.article-card__headline .article-title')
                if not title_elem:
                    title_elem = card.select_one('.article-card__headline')
                
                article_title = title_elem.get_text(strip=True) if title_elem else ''
                
                link_elem = card.select_one('.article-card__headline')
                link = link_elem.get('href') if link_elem else ''
                
                # 来源
                source_elem = card.select_one('.article-publisher__name')
                source = source_elem.get_text(strip=True) if source_elem else ''
                
                # 时间
                time_elem = card.select_one('.article-publisher__timestamp')
                time_text = time_elem.get_text(strip=True) if time_elem else ''
                
                # 标签
                tags = []
                for tag_elem in card.select('.supplemental__tags .tag'):
                    tags.append(tag_elem.get_text(strip=True))
                
                # 国家标志
                flag_elem = card.select_one('.flag img')
                country = flag_elem.get('src', '').split('/')[-1].replace('.png', '') if flag_elem else ''
                
                if article_title and link:
                    all_articles.append({
                        'title': article_title,
                        'link': link,
                        'source': source,
                        'time_text': time_text,
                        'tags': tags,
                        'country': country,
                        'type': 'top'
                    })
            
            # 提取 Latest News
            latest_articles = soup.select('.newsfeed--latest .article')
            existing_titles = {a['title'] for a in all_articles}
            
            for article in latest_articles[:30]:
                card = article.select_one('.article-card')
                if not card:
                    continue
                
                title_elem = card.select_one('.article-card__headline')
                article_title = title_elem.get_text(strip=True) if title_elem else ''
                
                if article_title in existing_titles:
                    continue
                
                link_elem = card.select_one('.article-card__headline')
                link = link_elem.get('href') if link_elem else ''
                
                source_elem = card.select_one('.article-publisher__name')
                source = source_elem.get_text(strip=True) if source_elem else ''
                
                time_elem = card.select_one('.article-publisher__timestamp')
                time_text = time_elem.get_text(strip=True) if time_elem else ''
                
                # Latest 新闻也有标签
                tags = []
                for tag_elem in card.select('.supplemental__tags .tag'):
                    tags.append(tag_elem.get_text(strip=True))
                
                flag_elem = card.select_one('.flag img')
                country = flag_elem.get('src', '').split('/')[-1].replace('.png', '') if flag_elem else ''
                
                if article_title and link:
                    all_articles.append({
                        'title': article_title,
                        'link': link,
                        'source': source,
                        'time_text': time_text,
                        'tags': tags,
                        'country': country,
                        'type': 'latest'
                    })
            
            # 提取 Popular News（如果有）
            popular_articles = soup.select('.newsfeed--popular .article')
            for article in popular_articles[:15]:
                card = article.select_one('.article-card')
                if not card:
                    continue
                
                # Popular 新闻有 data-count 属性表示排名
                rank = card.get('data-count', '')
                
                title_elem = card.select_one('.article-card__headline')
                article_title = title_elem.get_text(strip=True) if title_elem else ''
                
                if article_title in existing_titles:
                    continue
                
                link_elem = card.select_one('.article-card__headline')
                link = link_elem.get('href') if link_elem else ''
                
                source_elem = card.select_one('.article-publisher__name')
                source = source_elem.get_text(strip=True) if source_elem else ''
                
                time_elem = card.select_one('.article-publisher__timestamp')
                time_text = time_elem.get_text(strip=True) if time_elem else ''
                
                if article_title and link:
                    all_articles.append({
                        'title': article_title,
                        'link': link,
                        'source': source,
                        'time_text': time_text,
                        'tags': [],
                        'country': '',
                        'type': 'popular',
                        'rank': rank
                    })
            
            return {
                'title': title,
                'description': description,
                'link': url,
                'articles': all_articles
            }


def parse_article(article, feed_title):
    """解析单条新闻数据"""
    item = {}
    
    # 清理标题
    title = re.sub(r'\s+', ' ', article.get('title', '')).strip()
    item['title'] = title[:120] + '...' if len(title) > 120 else title
    
    # 生成描述（包含来源、标签、国家）
    description_parts = []
    if article.get('source'):
        description_parts.append(f'<strong>来源:</strong> {article["source"]}')
    if article.get('country'):
        description_parts.append(f'<strong>地区:</strong> {article["country"]}')
    if article.get('tags'):
        description_parts.append(f'<strong>标签:</strong> {", ".join(article["tags"])}')
    
    description = '<br>'.join(description_parts) if description_parts else '暂无摘要'
    item['description'] = description
    
    # 链接（处理相对路径）
    link = article.get('link', '')
    if link and link.startswith('/'):
        link = urljoin('https://www.newsnow.co.uk', link)
    item['link'] = link
    
    # 发布时间
    time_text = article.get('time_text', '')
    item['pubDate'] = parse_time_text(time_text)
    
    # 作者
    item['author'] = article.get('source', feed_title)
    
    # 分类（用于 RSS category 字段）
    if article.get('tags'):
        item['category'] = article['tags']
    
    return item


def parse_time_text(text):
    """解析 NewsNow 的时间格式
    支持格式: "33m", "7h", "09:40", "2d", "19:52 Mon, 16 Mar"
    """
    if not text:
        return arrow.now().isoformat()
    
    text = text.strip()
    
    # 匹配 "33m", "7h" 格式
    match = re.match(r'^(\d+)([hm])$', text)
    if match:
        val = int(match.group(1))
        unit = match.group(2)
        now = arrow.now()
        if unit == 'h':
            return now.shift(hours=-val).isoformat()
        if unit == 'm':
            return now.shift(minutes=-val).isoformat()
    
    # 匹配 "2d" 格式
    match = re.match(r'^(\d+)d$', text)
    if match:
        val = int(match.group(1))
        return arrow.now().shift(days=-val).isoformat()
    
    # 匹配 "09:40" 格式
    match = re.match(r'^(\d{1,2}):(\d{2})$', text)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        now = arrow.now()
        result = now.replace(hour=hours, minute=minutes, second=0)
        if result > now:
            result = result.shift(days=-1)
        return result.isoformat()
    
    # 匹配 "19:52 Mon, 16 Mar" 格式
    match = re.match(r'^(\d{1,2}):(\d{2})\s+(\w+),\s+(\d+)\s+(\w+)$', text)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        day = int(match.group(4))
        month = match.group(5)
        
        month_map = {
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
        }
        month_num = month_map.get(month, 1)
        
        year = arrow.now().year
        result = arrow.get(year, month_num, day, hours, minutes)
        if result > arrow.now():
            result = result.shift(years=-1)
        return result.isoformat()
    
    return arrow.now().isoformat()


def ctx():
    """
    主函数 - RSSHub Python 版本的标准入口
    """
    if not HAS_PLAYWRIGHT:
        return {
            'title': 'NewsNow AI News (Playwright not available)',
            'link': 'https://www.newsnow.co.uk/h/Science/AI',
            'description': 'Playwright is not available. Please install playwright: pip install playwright && playwright install chromium',
            'author': 'RSSHub',
            'items': [{
                'title': 'Playwright not available',
                'description': 'This feed requires Playwright. Please install playwright: pip install playwright && playwright install chromium',
                'link': 'https://www.newsnow.co.uk/h/Science/AI'
            }]
        }
    
    # 获取新闻数据
    result = asyncio.run(get_ai_news())
    
    # 解析文章列表
    items = [parse_article(article, result['title']) for article in result['articles']]
    
    # 统计信息
    top_count = len([a for a in result['articles'] if a['type'] == 'top'])
    latest_count = len([a for a in result['articles'] if a['type'] == 'latest'])
    
    return {
        'title': result['title'],
        'link': result['link'],
        'description': f'{result["description"]} (Top: {top_count}, Latest: {latest_count})',
        'author': 'NewsNow Aggregator',
        'items': items
    }


# 支持带参数的路由（用于不同分类）
def ctx_with_params(category=None):
    """支持参数的路由函数"""
    if category and category.lower() == 'ai':
        return ctx()
    return {
        'title': 'NewsNow - News',
        'link': 'https://www.newsnow.co.uk',
        'description': 'NewsNow news aggregator',
        'author': 'RSSHub',
        'items': []
    }