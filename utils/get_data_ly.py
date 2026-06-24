"""
航班搜索原始数据抓取 - 同程旅行(ly.com)
依赖：playwright (需安装: pip install playwright && playwright install chromium)
功能：输入出发地/目的地/日期，返回 FlightListSearch 接口的完整 JSON 响应
"""

from playwright.sync_api import sync_playwright
import json
import time
from datetime import datetime, date
from typing import Optional, Dict
from playwright.sync_api import expect

def ly_raw_data() -> tuple:
    """
    获取航班搜索原始响应数据
    通过加载config.json获取配置
    :return:           接口返回的 JSON 数据，失败返回 None
    """
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config["headless"], args=['--disable-blink-features=AutomationControlled'])
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        # 定义保存原始数据的空字典
        capture_container = {"response": None}
        html_container = {"response": ""}


        def on_response(response):
            # 匹配包含航班数据的响应HTML
            if "https://www.ly.com/flights/itinerary/oneway/" in response.url and response.request.method == "GET":
                if response.status == 200:
                    print("捕获到HTML数据")
                    try:
                        html_container["response"] = str(response.text())
                    except Exception as e:
                        print(f"解析 HTML 失败: {e}")
            # 匹配包含航班数据的响应json
            if "getflightlist" in response.url and response.request.method == "POST":
                if response.status == 200:
                    print("捕获到json数据")
                    try:
                        res_body = response.json()
                        if res_body:
                            capture_container["response"] = res_body
                            # print(f"成功捕获 API 数据，长度: {len(str(res_body))}")
                    except Exception as e:
                        print(f"解析 JSON 失败: {e}")

        context.on("response", on_response)
        page = context.new_page()

        # 1. 访问首页
        print("正在加载航班搜索页...")
        page.goto("https://www.ly.com", wait_until='domcontentloaded', timeout=10000)
        time.sleep(5)  # 等待页面稳定

        # 1.1 关闭弹窗
        try:
            page.locator('img[class="dt-close-icon closeDtMask"]').first.click()
            time.sleep(1)
        except Exception:
            pass

        #1.5 点击单程
        page.locator('label[for="airplaneInternatRadio1"]').click()
        time.sleep(1)

        # 出发地
        depart_input = page.locator('input[name="iOrgPort"]').first
        depart_input.click()
        depart_input.press_sequentially(config["depart"], delay=120)
        # 等待下拉框出现
        time.sleep(1)
        # 点击第一个建议（通常为城市）
        page.locator('.flight_search_Wrap .flight_search_tray tr').first.click()
        # 按 Tab 键移动到目的地输入框，同时关闭出发地下拉框
        page.keyboard.press("Tab")
        time.sleep(1)  # 等待下拉框消失

        # 目的地
        arrive_input = page.locator('input[name="iArvPort"]').first
        arrive_input.click()
        arrive_input.press_sequentially(config["arrive"], delay=120)
        # 等待目的地下拉框出现
        time.sleep(1)
        # 在可见的下拉框中点击第一项
        page.locator('.flight_search_Wrap:visible .flight_search_tray tr').first.click()
        time.sleep(1)  # 等待下拉框消失

        # 4. 选择出发日期
        depart_date = f"{config['year']}-{config['month']}-{config['day']}"
        print(f"出发日期: {depart_date}")
        page.locator('input[name="idtGoDate"]').click()
        time.sleep(1)
        try:
            max_attempts = 12
            while max_attempts > 0 and page.get_by_text(f"{int(config['year'])}年{int(config['month'])}月").count() == 0:
                page.locator('.next-month-panel i.next-month').click()
                page.locator('.month-panel .month').first.wait_for(state='visible', timeout=3000)
                max_attempts -= 1
            page.locator(f'td[data-date="{depart_date}"]').first.click()
        except Exception as e:
            print(f"日期选择失败，请检查输入日期！", e)
        time.sleep(1)

        # 5. 点击搜索按钮
        print("正在提交搜索...")
        page.locator('input[id="iflightSubmit"]').first.click()

        # 6. 等待目标响应出现
        print("等待航班数据返回...")
        max_wait = 40 
        start_time = time.time()
        
        batchSearch_response = None  # 初始化 batchSearch_response
        while time.time() - start_time < max_wait:
            # 检查元素是否存在（即使隐藏也算存在）
            if page.locator('#bbz-accounts-pc-global-maskLogin').count() > 0:
                print("检测到登录弹窗，刷新页面")
                page.reload()
                page.wait_for_load_state("networkidle")  # 等待页面加载完成
                continue                         
            # 当 "response" 不为 None 时开始分析数据
            if html_container["response"]:
                time.sleep(5)  # 等待页面稳定
                if capture_container["response"]:
                    print("开始分析数据")                
                    try:                    
                        batchSearch_response = capture_container["response"]
                        #"resDesc"为请求成功且"FlightInfoSimpleList"在响应体中说明获取到有效数据
                        if batchSearch_response.get("resDesc") == "请求成功" and "FlightInfoSimpleList" in batchSearch_response.get("body", {}):
                            print("获取到有效数据！")
                            if config["dump_raw_data"]:
                                # 保存到文件
                                filename1 = f"./raw_data/ly_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                                with open(filename1, "w", encoding="utf-8") as f:
                                    json.dump(batchSearch_response, f, indent=2, ensure_ascii=False)
                                print("数据已保存到", filename1)
                                filename2 = f"./raw_data/ly_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                                with open(filename2, "w", encoding="utf-8") as f:
                                    f.write(html_container["response"])
                                print("数据已保存到", filename2)
                            break
                        else:
                            raise ValueError("未获取到有效数据，可能遇到人机验证或请求异常")

                    except Exception as e:
                        print(batchSearch_response)
                        print("数据异常！",e)       

            time.sleep(0.5) # 循环检测间隔

        else:
            print("未捕获到目标数据。")

        
        browser.close()
        
        return (batchSearch_response, html_container)


if __name__ == "__main__":
    ly_raw_data()
  