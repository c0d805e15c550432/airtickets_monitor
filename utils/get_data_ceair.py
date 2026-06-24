"""
航班搜索原始数据抓取 - 中国东方航空(ceair.com)
依赖：playwright (需安装: pip install playwright && playwright install chromium)
功能：输入出发地/目的地/日期，返回 FlightListSearch 接口的完整 JSON 响应
"""

from playwright.sync_api import sync_playwright
import json
import time
from datetime import datetime, date
from typing import Optional, Dict
from playwright.sync_api import expect

def select_calendar_date(page, target_year: int, target_month: int, target_day: int):
    """
    在自定义日历中选择指定日期
    :param page: Playwright 页面对象
    :param target_year: 目标年份，如 2026
    :param target_month: 目标月份，1~12
    :param target_day: 目标日期，1~31
    """
    # 定位整个日历容器（确保日历已打开）
    page.locator('input[class="ceair-input__inner"]').first.click()  # 点击触发日历显示
    time.sleep(1)  # 等待日历动画完成

    # 最多尝试 12 次切换月份，防止无限循环
    for _ in range(12):
        # 获取左侧面板的年月
        left_year_elem = page.locator("#ceair-group .thisyear").first
        left_month_elem = page.locator("#ceair-group .thismonth").first
        left_year = int(left_year_elem.text_content().strip().rstrip("-"))
        left_month = int(left_month_elem.text_content().strip())

        # 获取右侧面板的年月
        right_year_elem = page.locator("#ceair-group-right .thisyear").first
        right_month_elem = page.locator("#ceair-group-right .thismonth").first
        right_year = int(right_year_elem.text_content().strip().rstrip("-"))
        right_month = int(right_month_elem.text_content().strip())

        # 检查目标日期在左侧还是右侧
        target_panel = None
        if left_year == target_year and left_month == target_month:
            target_panel = page.locator("#ceair-group")
        elif right_year == target_year and right_month == target_month:
            target_panel = page.locator("#ceair-group-right")

        if target_panel:
            # 在目标面板中定位日期，避免价格文本包含目标日导致误匹配
            day_texts = {str(target_day), f"{target_day:02d}"}
            day_values = target_panel.locator(".days [date='item'] .date-value")
            for idx in range(day_values.count()):
                cell = day_values.nth(idx)
                tokens = [token.strip() for token in cell.inner_text().split() if token.strip()]
                if not any(token in day_texts for token in tokens):
                    continue
                parent_cell = cell.locator("xpath=ancestor::div[@date='item']")
                parent_class = parent_cell.get_attribute("class") or ""
                if "unAble" in parent_class:
                    raise Exception(f"日期 {target_year}-{target_month}-{target_day} 不可选")
                cell.click()
                print(f"成功选择日期：{target_year}-{target_month}-{target_day}")
                return

        # 未找到目标月份，切换月份
        current_total = left_year * 12 + left_month
        target_total = target_year * 12 + target_month
        if target_total < current_total:
            prev_btn = page.locator("#prev")
            prev_btn.click()
        else:
            next_btn = page.locator("#next")
            next_btn.click()
        # 等待切换动画或内容更新
        page.wait_for_timeout(500)

    raise Exception(f"未能找到目标月份 {target_year}-{target_month}，请检查日历范围")  

def ceair_raw_data() -> Optional[Dict]:
    """
    获取航班搜索原始响应数据
    通过加载config.json获取配置
    :return:           接口返回的 JSON 数据，失败返回 None
    """
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)
        config["headless"] = False 

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config["headless"])
        context = browser.new_context()
        

# 1. 修改容器结构，初始值设为空字典
        capture_container = {"response": None}

        def on_response(response):
            # 2. 检查具体的 API 路径
            if "shopping/briefInfo" in response.url and response.request.method == "POST":
                if response.status == 200:
                    try:
                        res_body = response.json()
                        if res_body.get("resultCode", "") == "S200":
                            capture_container["response"] = res_body
                            # print(res_body[:100])  # 打印前500字符预览
                    except Exception as e:
                        print(f"解析 JSON 失败: {e}")
                        print(f"响应文本: {response.text()}")  # 打印前500字符预览

        context.on("response", on_response)
        page = context.new_page()

        # 1. 访问首页
        print("正在加载航班搜索页...")
        page.goto("https://www.ceair.com/zh/cny/home", wait_until="networkidle", timeout=10000)
        time.sleep(1)  # 等待页面稳定


        # 2. 填写出发地
        print(f"出发地: {config["depart"]}")
        page.locator('input[aria-label="出发"]').first.fill(config["depart"])
        time.sleep(1)
        # 等待下拉框出现并选择第一个（通常自动补全）
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        time.sleep(1)

        # 3. 填写目的地
        print(f"目的地: {config["arrive"]}")
        page.locator('input[aria-label="到达"]').first.fill(config["arrive"])
        time.sleep(1)
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        time.sleep(1)

        # 4. 选择出发日期
        print(f"出发日期: {config["year"]+config["month"]+config["day"]}")
        select_calendar_date(page, int(config["year"]), int(config["month"]), int(config["day"]))

        # 5. 点击搜索按钮
        print("正在提交搜索...")
        page.locator('button[class="ceair-button submit-btn new-but-medium new-back-pattern-two ceair-button--danger ceair-button--medium is-round"]').first.click()

        # 6. 等待目标响应出现
        print("等待航班数据返回...")
        max_wait = 60
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            # 检查元素是否存在（即使隐藏也算存在）
            if page.locator('#bbz-accounts-pc-global-maskLogin').count() > 0:
                print("检测到登录弹窗，刷新页面")
                page.reload()
                page.wait_for_load_state("networkidle")  # 等待页面加载完成
                continue                         
            # 当 "response" 不为 None 时开始分析数据
            if capture_container["response"] is not None:
                print("开始分析数据")                
                try:                    
                    batchSearch_response = capture_container["response"]

                    if "flightItems" in batchSearch_response["data"]:
                        print("获取到有效数据！")
                        if config["dump_raw_data"]:
                            # 保存到文件
                            filename = f"./raw_data/ceair_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                            with open(filename, "w", encoding="utf-8") as f:
                                json.dump(batchSearch_response, f, indent=2, ensure_ascii=False)
                            print("数据已保存到", filename)
                        break
                    else:
                        raise ValueError("未知错误")
                except Exception as e:
                    # print(batchSearch_response)
                    print("数据异常！",e)       

            time.sleep(0.5) # 循环检测间隔

        else:
            print("未捕获到目标数据。")

        
        browser.close()
        
        return capture_container["response"]


if __name__ == "__main__":
    raw_data = ceair_raw_data()
    print(raw_data)
    
