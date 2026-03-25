# rsshub/spiders/newsnow/ai.py
import re
import asyncio
import arrow
try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
from bs4 import BeautifulSoup
from urllib.parse import urljoin

async def get_ai_news(tag):
    """使用 Playwright 获取 NewsNow AI 新闻"""
    async with async_playwright() as p:
        async with await p.chromium.launch(
            headless=True,
            # executable_path='C:\Program Files\Google\Chrome\Application\chrome.exe',
            args=['--no-sandbox', '--disable-dev-shm-usage']
        ) as browser:
            page = await browser.new_page()
            
            # 设置反检测
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            await page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })

            # 拦截不必要的资源
            # ========== 白名单模式：只允许 newsnow.co.uk ==========
            # 检查是否是 CSS 或图片资源（支持带查询参数的 URL）
            async def allow_only_newsnow(route):
                """只允许访问 newsnow.co.uk 的请求"""
                url = route.request.url
                is_css_or_image = re.search(r'\.(png|jpg|jpeg|gif|svg|webp|ico)(\?|$)', url, re.IGNORECASE)
                
                # 只允许 newsnow.co.uk 域名
                if 'newsnow.co.uk' in url and not is_css_or_image:
                    await route.continue_()
                else:
                    await route.abort()
            
            # 拦截所有请求，只放行 newsnow.co.uk
            await page.route("**/*", allow_only_newsnow)
            # ===================================================
            
            
            try:
                url = f"https://www.newsnow.co.uk/{tag}"
                await page.goto(url, wait_until='networkidle')
                await page.wait_for_selector('.article', timeout=5000)
                
                # 模拟滚动加载更多内容
                for _ in range(3):
                    await smooth_scroll_to_bottom(page, steps=4, delay=0.5)
                    await asyncio.sleep(2)
                    await page.wait_for_load_state('networkidle', timeout=10000)
                
                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                all_articles = []
                title = 'NewsNow - AI News'
                description = '最新人工智能新闻聚合'
                feed_link = url

                # 直接查找所有带有 rel="nofollow" 的 a 标签
                nofollow_links = soup.select('a[rel="nofollow"]')
                print(f"找到 {len(nofollow_links)} 个 nofollow 链接")

                for link in nofollow_links:
                    # 获取链接
                    link_url = link.get('href', '')
                    
                    # 获取标题（链接文本）
                    title_text = link.get_text(strip=True)
                    
                    if not title_text or not link_url:
                        continue
                    
                    # 尝试获取额外的信息（可选）
                    # 查找父级元素中的来源、时间等
                    parent = link.find_parent()
                    source = ''
                    time_text = ''
                    tags = []
                    country = ''
                    has_paywall = False
                    
                    # 尝试获取来源信息
                    source_elem = parent.select_one('.article-publisher__name') if parent else None
                    if source_elem:
                        source = source_elem.get_text(strip=True)
                    
                    # 尝试获取时间
                    time_elem = parent.select_one('.article-publisher__timestamp') if parent else None
                    if time_elem:
                        time_text = time_elem.get_text(strip=True)
                    
                    # 尝试获取标签
                    if parent:
                        for tag_elem in parent.select('.supplemental__tags .tag'):
                            tags.append(tag_elem.get_text(strip=True))
                    
                    # 尝试获取国家
                    flag_elem = parent.select_one('.flag img') if parent else None
                    if flag_elem:
                        country = flag_elem.get('src', '').split('/')[-1].replace('.png', '')
                        if '.' in country:
                            country = country.split('.')[0]
                    
                    # 检测付费墙
                    if parent:
                        has_paywall = parent.select_one('.paywall-icon-wrap') is not None
                    
                    all_articles.append({
                        'title': title_text,
                        'link': link_url,
                        'source': source,
                        'time_text': time_text,
                        'tags': tags,
                        'country': country,
                        'has_paywall': has_paywall
                    })
                
                print(f"最终提取到 {len(all_articles)} 篇文章")
                
                return {
                    'title': title,
                    'description': description,
                    'link': feed_link,
                    'articles': all_articles
                }
                
            except Exception as e:
                print(f"Error fetching NewsNow AI news: {e}")
                return {
                    'title': 'NewsNow - AI News',
                    'description': '获取新闻失败',
                    'link': 'https://www.newsnow.co.uk/h/Science/AI',
                    'articles': []
                }

async def smooth_scroll_to_bottom(page, steps=10, delay=0.1):
    """分段平滑滚动到底部"""
    # 获取页面总高度
    total_height = await page.evaluate("document.body.scrollHeight-300")
    
    # 获取当前滚动位置
    current_scroll = await page.evaluate("window.pageYOffset")
    
    # 计算每步滚动的距离
    step_distance = (total_height - current_scroll) / steps
    
    for i in range(1, steps + 1):
        scroll_to = current_scroll + (step_distance * i)
        await page.evaluate(f"""
            window.scrollTo({{
                top: {scroll_to},
                behavior: 'smooth'
            }});
        """)
        await asyncio.sleep(delay)
    
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight-300)")

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


def parse_article(article, feed_title):
    """解析单条新闻数据，付费文章返回 None"""
    # 检查是否有付费墙
    if article.get('has_paywall'):
        return None
    
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
    
    item['description'] = '<br>'.join(description_parts) if description_parts else '暂无摘要'
    
    # 链接
    item['link'] = article.get('link', '')
    
    # 发布时间
    time_text = article.get('time_text', '')
    item['pubDate'] = parse_time_text(time_text)
    
    # 作者
    item['author'] = article.get('source', feed_title)
    
    return item


def ctx(tag):
    """主函数 - RSSHub Python 标准入口"""
    if not HAS_PLAYWRIGHT:
        return {
            'title': 'NewsNow AI News (Playwright not available)',
            'link': 'https://www.newsnow.co.uk/h/Science/AI',
            'description': 'Playwright is not available. Please install playwright: pip install playwright && playwright install chromium',
            'author': 'RSSHub',
            'items': [{
                'title': 'Playwright not available',
                'description': 'This feed requires Playwright. Please run: playwright install chromium',
                'link': f'https://www.newsnow.co.uk/{tag}',
                'pubDate': arrow.now().isoformat()
            }]
        }

    result = asyncio.run(get_ai_news(tag))
    
    items = []
    for article in result['articles']:
        parsed = parse_article(article, result['title'])
        if parsed is not None:
            items.append(parsed)
    
    # 统计信息
    total = len(items)
    paid = len([a for a in result['articles'] if a.get('has_paywall')])
    
    return {
        'title': result['title'],
        'link': result['link'],
        'description': f"{result['description']} (共 {total} 篇，过滤付费文章 {paid} 篇)",
        'author': 'NewsNow Aggregator',
        'items': items
    }