#!/usr/bin/env python
"""
国家法律法规数据库批量下载脚本 - Playwright 自动化 (修复版)
"""

import asyncio
import os
import re
import shutil
from pathlib import Path
from playwright.async_api import async_playwright, Download

# 目标目录
OUTPUT_DIR = Path(r"G:\claude code\.claude\Law\RAG")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 下载临时目录
TEMP_DIR = Path.home() / "Downloads"

# 下载目标
TARGET_COUNT = 1000  # 目标数量

# 分类和数量分配（按优先级）
CATEGORIES = [
    {"name": "法律", "count": 350, "url_pattern": "法律310"},
    {"name": "行政法规", "count": 350, "url_pattern": "行政法规610"},
    {"name": "司法解释", "count": 250, "url_pattern": "司法解释561"},
    {"name": "宪法", "count": 50, "url_pattern": "宪法"},
]


async def download_laws():
    """批量下载法律文档"""
    downloaded_count = 0
    downloaded_titles = set()

    # 检查已下载的文件（只检查真实法律）
    existing_files = list(OUTPUT_DIR.glob("中华人民共和国*.docx"))
    for f in existing_files:
        # 从文件名提取标题
        title = re.sub(r'[-_]\d{8}$', '', f.stem)
        downloaded_titles.add(title)
    print(f"[INFO] 已存在 {len(existing_files)} 个真实法律文件，跳过已下载的")

    async with async_playwright() as p:
        # 启动浏览器（非无头模式便于调试）
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        # 访问首页
        print("[INFO] 打开国家法律法规数据库...")
        await page.goto("https://flk.npc.gov.cn", wait_until="networkidle")
        await asyncio.sleep(3)

        # 遍历分类下载
        for category in CATEGORIES:
            if downloaded_count >= TARGET_COUNT:
                break

            cat_name = category["name"]
            cat_target = category["count"]
            url_pattern = category["url_pattern"]

            print(f"\n{'='*60}")
            print(f"[INFO] 开始下载 {cat_name} 分类，目标 {cat_target} 部...")
            print(f"{'='*60}")

            try:
                # 点击分类进入搜索页
                await page.click(f"text={url_pattern}")
                await asyncio.sleep(3)

                # 等待新标签页
                pages = context.pages
                if len(pages) > 1:
                    search_page = pages[-1]
                else:
                    search_page = page

                # 筛选"有效"状态
                print("[INFO] 筛选有效状态...")
                try:
                    await search_page.click("label:has-text('有效')", timeout=5000)
                    await asyncio.sleep(2)
                except Exception as e:
                    print(f"[WARN] 点击有效筛选失败: {e}")

                # 获取总条数
                try:
                    total_text = await search_page.locator("text=/共 \\d+ 条/").inner_text(timeout=5000)
                    total_match = re.search(r'(\d+)', total_text)
                    total = int(total_match.group(1)) if total_match else 0
                    print(f"[INFO] {cat_name} 有效状态共 {total} 条")
                except:
                    total = 0
                    print(f"[WARN] 无法获取总数")

                # 逐页下载
                page_num = 1
                category_downloaded = 0

                while category_downloaded < cat_target and downloaded_count < TARGET_COUNT:
                    # 获取当前页的法律列表
                    try:
                        # 尝试多种定位方式
                        items = await search_page.locator(".result-item").all()
                        if not items:
                            items = await search_page.locator("[class*='result']").all()
                        if not items:
                            # 尝试获取所有包含标题的元素
                            items = await search_page.locator("a[href*='detail']").all()
                    except:
                        items = []

                    print(f"[INFO] 第 {page_num} 页，找到 {len(items)} 个条目")

                    for i, item in enumerate(items[:20]):  # 每页最多处理20个
                        if category_downloaded >= cat_target or downloaded_count >= TARGET_COUNT:
                            break

                        try:
                            # 点击条目进入详情页
                            await item.click()
                            await asyncio.sleep(2)

                            # 检查是否打开了新标签页
                            detail_pages = context.pages
                            if len(detail_pages) > 2:
                                detail_page = detail_pages[-1]
                            else:
                                detail_page = search_page

                            # 获取标题
                            try:
                                title_elem = await detail_page.locator("h1, .title, [class*='title']").first.inner_text(timeout=5000)
                                title = title_elem.strip()
                            except:
                                # 从 URL 获取标题
                                url = detail_page.url
                                title_match = re.search(r'title=([^&]+)', url)
                                if title_match:
                                    title = title_match.group(1)
                                else:
                                    title = f"法律_{downloaded_count+1}"

                            clean_title = re.sub(r'[<>:"/\\|?*]', '', title)[:50]

                            # 检查是否已下载
                            if title in downloaded_titles or clean_title in downloaded_titles:
                                print(f"[SKIP] 已下载: {clean_title[:30]}...")
                                if len(detail_pages) > 2:
                                    await detail_page.close()
                                continue

                            # 点击下载按钮
                            try:
                                await detail_page.click("button:has-text('下载')", timeout=5000)
                                await asyncio.sleep(1)

                                # 点击"点击下载"
                                await detail_page.click("text=点击下载", timeout=5000)

                                # 等待下载完成
                                download = await detail_page.wait_for_event("download", timeout=15000)
                                await download.save_as(OUTPUT_DIR / f"{clean_title}.docx")

                                print(f"[OK] 下载成功 ({downloaded_count+1}): {clean_title[:40]}...")
                                downloaded_titles.add(title)
                                downloaded_count += 1
                                category_downloaded += 1

                            except Exception as dl_error:
                                print(f"[FAIL] 下载失败: {clean_title[:30]}... - {dl_error}")

                            # 关闭详情页
                            if len(detail_pages) > 2:
                                await detail_page.close()
                            await asyncio.sleep(0.5)

                        except Exception as e:
                            print(f"[ERROR] 处理条目失败: {e}")
                            continue

                    # 下一页
                    try:
                        next_btn = search_page.locator("button:has-text('下一页'), text=下一页")
                        if await next_btn.is_visible(timeout=3000):
                            await next_btn.click()
                            await asyncio.sleep(2)
                            page_num += 1
                        else:
                            print("[INFO] 无下一页，结束该分类")
                            break
                    except:
                        print("[INFO] 无法找到下一页按钮")
                        break

            except Exception as e:
                print(f"[ERROR] 分类 {cat_name} 处理失败: {e}")

        await browser.close()

    print(f"\n{'='*60}")
    print(f"[DONE] 完成！共下载 {downloaded_count} 部法律法规")
    print(f"[INFO] 文件保存在: {OUTPUT_DIR}")

    # 统计真实法律文档数量
    real_laws = list(OUTPUT_DIR.glob("中华人民共和国*.docx"))
    print(f"[INFO] 目录中真实法律文档: {len(real_laws)} 个")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(download_laws())