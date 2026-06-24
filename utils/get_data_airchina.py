"""
航班搜索原始数据抓取 - 中国国际航空(airchina.com)
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
    calendar_modal = page.locator(".styles_calendarModal__GfAJ0").first
    if not calendar_modal.is_visible():
        open_selectors = [
            'input[placeholder="出发日期"]',
            'input[placeholder="出发"]',
            'input[placeholder="出发机场"]',
            "input[type='date']",
        ]
        for selector in open_selectors:
            locator = page.locator(selector).first
            if locator.count() > 0 and locator.is_visible():
                locator.click()
                break
        time.sleep(0.5)

    page.wait_for_selector(".styles_calendarModal__GfAJ0", state="visible", timeout=10000)

    panels = page.locator(".styles_calendarPanel__0I8da")

    def get_panel_year_month(panel_locator) -> tuple[int, int]:
        year_text = panel_locator.locator(".style_calendarYearBtn__3VAaw").first.inner_text().strip()
        month_text = panel_locator.locator(".style_calendarMonthBtn____ZgL").first.inner_text().strip()
        year = int(year_text.replace("年", "").strip())
        month = int(month_text.replace("月", "").strip())
        return year, month

    for _ in range(24):
        left_panel = panels.nth(0)
        right_panel = panels.nth(1)
        left_year, left_month = get_panel_year_month(left_panel)
        right_year, right_month = get_panel_year_month(right_panel)

        target_panel = None
        if (left_year, left_month) == (target_year, target_month):
            target_panel = left_panel
        elif (right_year, right_month) == (target_year, target_month):
            target_panel = right_panel

        if target_panel:
            date_spans = target_panel.locator(".styles_calendarInnerBodyDate__FtQmn")
            for idx in range(date_spans.count()):
                span = date_spans.nth(idx)
                if span.inner_text().strip() != str(target_day):
                    continue
                cell = span.locator("xpath=ancestor::td[1]")
                cell.click()
                print(f"成功选择日期：{target_year}-{target_month}-{target_day}")
                return

            raise Exception(f"未找到目标日期 {target_year}-{target_month}-{target_day}")

        if (target_year, target_month) > (right_year, right_month):
            page.locator(".styles_calendarHeaderNextBtn__5K1R6").first.click()
        else:
            page.locator(".styles_calendarHeaderPrevBtn__gwY9V").first.click()
        page.wait_for_timeout(500)

    raise Exception(f"未能找到目标月份 {target_year}-{target_month}，请检查日历范围")

def airchina_raw_data() -> Optional[Dict]:
    """
    获取航班搜索原始响应数据
    通过加载config.json获取配置
    :return:           接口返回的 JSON 数据，失败返回 None
    """
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config["headless"])
        context = browser.new_context()
        

# 1. 修改容器结构，初始值设为空字典
        capture_container = {"response": None}

        def on_response(response):
            # 2. 检查具体的 API 路径
            if "gateway/api/flight/list" in response.url and response.request.method == "POST":
                if response.status == 200:
                    try:
                        res_body = response.json()
                        if res_body.get("Status", "") == "SUCCESS":
                            capture_container["response"] = res_body
                            # print(res_body[:100])  # 打印前500字符预览
                    except Exception as e:
                        print(f"解析 JSON 失败: {e}")
                        print(f"响应文本: {response.text()}")  # 打印前500字符预览

        context.on("response", on_response)
        page = context.new_page()

        # 1. 访问首页
        print("正在加载航班搜索页...")
        page.goto("https://www.airchina.com.cn/", wait_until="document_loaded", timeout=60000)
        time.sleep(1)  # 等待页面稳定


        # 2. 填写出发地
        print(f"出发地: {config["depart"]}")
        page.locator('input[placeholder="出发机场"]').first.fill(config["depart"])
        time.sleep(1)
        # 等待下拉框出现并选择第一个（通常自动补全）
        page.locator('.CitySelector_airportItem__hWwGi').first.click()
        time.sleep(1)

        # 3. 填写目的地
        print(f"目的地: {config["arrive"]}")
        page.locator('input[placeholder="到达机场"]').first.fill(config["arrive"])
        time.sleep(1)
        page.locator('.CitySelector_airportItem__hWwGi').first.click()
        time.sleep(1)

        # 4. 选择出发日期
        print(f"出发日期: {config["year"]+config["month"]+config["day"]}")
        page.locator('input[placeholder="出发日期"]').first.click()
        select_calendar_date(page, int(config["year"]), int(config["month"]), int(config["day"]))

        # 5. 点击搜索按钮
        print("正在提交搜索...")
        page.locator('text=查询').first.click()

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

                    if "Data" in batchSearch_response:
                        print("获取到有效数据！")
                        if config["dump_raw_data"]:
                            # 保存到文件
                            filename = f"./raw_data/airchina_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
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
        
        return batchSearch_response


if __name__ == "__main__":
    airchina_raw_data()
    
