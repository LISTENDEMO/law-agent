#!/usr/bin/env python
"""
国家法律法规数据库批量下载脚本 - Playwright 自动化
"""

import asyncio
import os
import re
import time
from pathlib import Path
from playwright.async_api import async_playwright

# 目标目录
OUTPUT_DIR = Path(r"G:\claude code\.claude\Law\RAG")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 下载目标
TARGET_COUNT = 1000  # 目标数量

# 分类和数量分配
CATEGORIES = [
    {"name": "宪法", "count": 50},
    {"name": "法律", "count": 350},
    {"name": "行政法规", "count": 350},
    {"name": "司法解释", "count": 250},
]


async def download_laws():
    """批量下载法律文档"""
    downloaded_count = 0
    downloaded_titles = set()

    # 检查已下载的文件
    existing_files = list(OUTPUT_DIR.glob("*.docx"))
    for f in existing_files:
        # 从文件名提取标题（去掉日期后缀）
        title = re.sub(r'_\d{8}$', '', f.stem)
        downloaded_titles.add(title)
    print(f"[INFO] 已存在 {len(existing_files)} 个文件，跳过已下载的")

    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch(headless=False)  # 非无头模式，便于调试
        context = await browser.new_context(
            accept_downloads=True,
            downloads_path=str(OUTPUT_DIR),
        )
        page = await context.new_page()

        # 访问首页
        print("[INFO] 打开国家法律法规数据库...")
        await page.goto("https://flk.npc.gov.cn", wait_until="networkidle")
        await asyncio.sleep(2)

        # 遍历分类下载
        for category in CATEGORIES:
            if downloaded_count >= TARGET_COUNT:
                break

            cat_name = category["name"]
            cat_target = category["count"]

            print(f"\n[INFO] 开始下载 {cat_name} 分类，目标 {cat_target} 部...")

            # 点击分类进入搜索页
            # 需要根据页面结构找到正确的元素
            try:
                # 点击分类链接（例如"法律310"）
                await page.click(f"text={cat_name}")
                await asyncio.sleep(2)

                # 等待新标签页
                pages = context.pages
                if len(pages) > 1:
                    search_page = pages[-1]
                else:
                    search_page = page

                # 在搜索页筛选"有效"状态
                print("[INFO] 筛选有效状态...")
                try:
                    await search_page.click("label:has-text('有效')")
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"[WARN] 点击有效筛选失败: {e}")

                # 获取总条数
                total_text = await search_page.locator("text=/共 \\d+ 条/").inner_text()
                total_match = re.search(r'(\d+)', total_text)
                total = int(total_match.group(1)) if total_match else 0
                print(f"[INFO] {cat_name} 有效状态共 {total} 条")

                # 逐页下载
                page_num = 1
                category_downloaded = 0

                while category_downloaded < cat_target and downloaded_count < TARGET_COUNT:
                    # 获取当前页的法律列表
                    items = await search_page.locator(".result-item, [class*='result']").all()
                    if not items:
                        # 尝试其他定位方式
                        items = await search_page.locator("text=/中华人民共和国/").all()

                    print(f"[INFO] 第 {page_num} 页，找到 {len(items)} 个条目")

                    for i, item in enumerate(items):
                        if category_downloaded >= cat_target or downloaded_count >= TARGET_COUNT:
                            break

                        try:
                            # 点击条目进入详情页
                            await item.click()
                            await asyncio.sleep(1)

                            # 检查是否打开了新标签页
                            detail_pages = context.pages
                            if len(detail_pages) > 2:
                                detail_page = detail_pages[-1]
                            else:
                                # 可能是当前页面跳转
                                detail_page = search_page

                            # 获取标题
                            title_elem = await detail_page.locator("h1, .title, [class*='title']").first.inner_text()
                            title = title_elem.strip()
                            clean_title = re.sub(r'[<>:"/\\|?*]', '', title)[:50]

                            # 检查是否已下载
                            if title in downloaded_titles or clean_title in downloaded_titles:
                                print(f"[SKIP] 已下载: {clean_title}")
                                if len(detail_pages) > 2:
                                    await detail_page.close()
                                continue

                            # 点击下载按钮
                            await detail_page.click("button:has-text('下载')")
                            await asyncio.sleep(0.5)

                            # 点击"点击下载"
                            await detail_page.click("text=点击下载")
                            await asyncio.sleep(2)

                            # 等待下载完成
                            download = await detail_page.wait_for_event("download", timeout=10000)
                            saved_path = await download.path()

                            # 重命名文件
                            new_name = f"{clean_title}.docx"
                            new_path = OUTPUT_DIR / new_name
                            if saved_path and saved_path.exists():
                                saved_path.rename(new_path)
                                print(f"[OK] 下载成功: {clean_title}")
                                downloaded_titles.add(title)
                                downloaded_count += 1
                                category_downloaded += 1

                            # 关闭详情页
                            if len(detail_pages) > 2:
                                await detail_page.close()

                        except Exception as e:
                            print(f"[ERROR] 下载失败: {e}")
                            # 继续下一个

                    # 下一页
                    try:
                        await search_page.click("button:has-text('下一页'), text=下一页")
                        await asyncio.sleep(1)
                        page_num += 1
                    except:
                        print("[INFO] 无下一页")
                        break

            except Exception as e:
                print(f"[ERROR] 分类 {cat_name} 处理失败: {e}")

        await browser.close()

    print(f"\n[DONE] 完成，共下载 {downloaded_count} 部法律法规")
    print(f"[INFO] 文件保存在: {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(download_laws())