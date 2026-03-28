import os
import asyncio
import requests 
import feedparser
import arrow

from rsshub.async_runner import async_runner
from rsshub.utils import set_cached_title
from rsshub.utils import get_cached_title


from rsshub.utils import DEFAULT_HEADERS

from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.tmt.v20180321 import tmt_client_async, models

async def batch_translate_titles(items_list, source='auto', target='zh', max_chars=5000):
    """批量翻译标题，自动分批处理，保持顺序"""
    if not items_list:
        return items_list
    
    # ========== 第一步：检查缓存，构建翻译队列 ==========
    # 用于存储翻译请求的列表（需要翻译的原文，不需要的用 None 占位）
    translate_requests = []  # 保持顺序，需要翻译的是原文，不需要的是 None
    need_translate_indices = []  # 记录需要翻译的位置索引
    
    for i, item in enumerate(items_list):
        original_title = item['title']
        cached = get_cached_title(original_title, source, target)
        
        if cached:
            # 命中缓存，直接赋值
            item['title'] = cached
            translate_requests.append(None)  # 占位，不需要翻译
        else:
            # 未命中，需要翻译
            translate_requests.append(original_title)
            need_translate_indices.append(i)
    
    # 统计缓存命中情况
    total = len(items_list)
    miss_count = len(need_translate_indices)
    hit_count = total - miss_count
    if total > 0:
        print(f"[Title Cache] Hit: {hit_count}/{total} ({hit_count*100//total}%)")
    
    # 如果没有需要翻译的，直接返回
    if miss_count == 0:
        return items_list
    
    # ========== 第二步：提取需要翻译的标题（按顺序） ==========
    need_translate_titles = [translate_requests[i] for i in need_translate_indices]
    
    # ========== 第三步：批量翻译需要翻译的标题 ==========
    combined_text = '\n'.join(need_translate_titles)
    total_chars = len(combined_text)
    
    # 翻译结果列表（保持 need_translate_titles 的顺序）
    translated_results = []
    
    if total_chars <= max_chars:
        # 直接批量翻译
        print(f"Translating {len(need_translate_titles)} titles in single batch")
        translated_results = await _translate_batch_text(need_translate_titles, source, target)
    else:
        # 需要分批翻译
        print(f"Text too long ({total_chars} chars), splitting into batches...")
        
        # 分批
        batches = []
        current_batch = []
        current_length = 0
        
        for title in need_translate_titles:
            title_length = len(title) + 1
            if current_length + title_length > max_chars and current_batch:
                batches.append(current_batch)
                current_batch = []
                current_length = 0
            
            current_batch.append(title)
            current_length += title_length
        
        if current_batch:
            batches.append(current_batch)
        
        print(f"Split into {len(batches)} batches")
        
        # 逐批翻译，收集结果
        for batch_idx, batch in enumerate(batches, 1):
            print(f"Translating batch {batch_idx}/{len(batches)} ({len(batch)} titles)")
            try:
                batch_results = await _translate_batch_text(batch, source, target)
                translated_results.extend(batch_results)
            except Exception as err:
                print(f"Batch {batch_idx} translation failed: {err}")
                # 失败时返回原文
                translated_results.extend(batch)
    
    # ========== 第四步：将翻译结果放回原位 ==========
    # 按 need_translate_indices 的顺序将翻译结果赋值回去
    for idx, original_title, translated in zip(need_translate_indices, need_translate_titles, translated_results):
        # 缓存翻译结果
        set_cached_title(original_title, source, target, translated)
        # 更新 item 的标题
        items_list[idx]['title'] = translated
    
    return items_list


async def _translate_batch_text(titles: list, source: str, target: str) -> list:
    """批量翻译文本，返回翻译结果列表"""
    if not titles:
        return []
    
    combined_text = '\n'.join(titles)
    
    try:
        cred = credential.Credential(
            os.getenv("TENCENTCLOUD_SECRET_ID"),
            os.getenv("TENCENTCLOUD_SECRET_KEY")
        )
        
        async with tmt_client_async.TmtClient(cred, "ap-beijing") as client:
            req = models.TextTranslateRequest()
            req.SourceText = combined_text
            req.Source = source
            req.Target = target
            req.ProjectId = 0
            
            resp = await client.TextTranslate(req)
            
            translated = resp.TargetText.split('\n')
            
            # 确保数量一致
            if len(translated) != len(titles):
                print(f"Warning: Translation count mismatch: {len(translated)} vs {len(titles)}")
                if len(translated) > len(titles):
                    translated = translated[:len(titles)]
                else:
                    translated.extend([''] * (len(titles) - len(translated)))
            
            return translated
            
    except Exception as err:
        print(f"Batch translation error: {err}")
        raise

def parse(post):
    item = {}
    item['title'] = post.title
    item['description'] = post.summary if hasattr(post,'summary') else post.title
    item['pubDate'] = post.published if post.has_key('published') else arrow.now().isoformat()
    item['link'] = post.link if hasattr(post,'link') else ''
    item['author'] = post.author if post.has_key('author') else ''
    return item

def ctx(feed_url=''):
    res = requests.get(feed_url,headers=DEFAULT_HEADERS,verify=False)
    feed = feedparser.parse(res.text)
    title = feed.feed.title
    description = feed.feed.subtitle if feed.feed.has_key('subtitle') \
        else feed.feed.title
    author = feed.feed.author if feed.feed.has_key('author') \
        else feed.feed.generator if feed.feed.has_key('generator') \
        else title
    posts = list(map(parse, feed.entries))
    
    translated_posts = async_runner.run(batch_translate_titles(posts))

    return {
        'title': title,
        'link': feed_url,
        'description': description,
        'author': author,
        'items': translated_posts
    }  