"""
航班搜索原始数据抓取 - 海南航空(hnair.com)
依赖：playwright (需安装: pip install playwright && playwright install chromium)
功能：输入出发地/目的地/日期，返回 FlightListSearch 接口的完整 JSON 响应
"""

from playwright.sync_api import sync_playwright
import json
import time
from datetime import datetime, date
from typing import Optional, Dict
from playwright.sync_api import expect

        

def hnair_raw_data() -> Optional[Dict]:
    """
    获取航班搜索原始响应数据
    通过加载config.json获取配置
    :return:           接口返回的 JSON 数据，失败返回 None
    """
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    #初始化浏览器
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config["headless"])
        context = browser.new_context()
        

# 1. 修改容器结构，初始值设为空字典
        capture_container = {"response": None}

        def on_response(response):
            # 2. 检查具体的 API 路径
            if "processNearByFlightSearch.do" in response.url:
                if response.status == 200:
                    try:
                        res_body = response.json()
                        if res_body:
                            capture_container["response"] = res_body
                            # print(res_body[:100])  # 打印前500字符预览
                    except Exception as e:
                        print(f"解析 JSON 失败: {e}")

        context.on("response", on_response)
        page = context.new_page()

        # 1. 访问首页
        print("正在加载航班搜索页...")
        page.goto("https://www.hnair.com/", wait_until="networkidle", timeout=10000)
        time.sleep(1)  # 等待页面稳定


        # 2. 填写出发地
        print(f"出发地: {config["depart"]}")
        inputbox = page.locator('input[id="from_city1"]').first
        inputbox.click()  # 点击输入框以触发可能的事件
        time.sleep(0.5)  # 等待可能的事件处理
        inputbox.type(config["depart"])
        time.sleep(1)
        # 等待下拉框出现并选择第一个（通常自动补全）
        # page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        time.sleep(1)

        # 3. 填写目的地
        print(f"目的地: {config["arrive"]}")
        page.locator('input[id="to_city1"]').first.type(config["arrive"])
        time.sleep(1)
        # page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        time.sleep(1)

        # 4. 选择出发日期
        depart_date = config["year"]+"-"+config["month"]+"-"+config["day"]
        print(f"出发日期: {depart_date}")
        page.locator('input[id="flightBeginDate1"]').first.fill(depart_date)

        # 4.5.点击直飞
        page.locator('text=只看直飞航班').first.click()

        # 5. 点击搜索按钮
        print("正在提交搜索...")
        page.locator("button[onclick='checkScNum();']").first.click()

        # 6. 等待目标响应出现
        print("等待航班数据返回...")
        max_wait = 40 
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
                    if config["dump_raw_data"]:
                        # 保存到文件
                        filename = f"./raw_data/hnair_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                        with open(filename, "w", encoding="utf-8") as f:
                            json.dump(batchSearch_response, f, indent=2, ensure_ascii=False)
                        print("数据已保存到", filename)
                    break
                except Exception as e:
                    # print(batchSearch_response)
                    print("数据异常！",e)       

            time.sleep(0.5) # 循环检测间隔

        else:
            print("未捕获到目标数据。")

        
        browser.close()
        
        return batchSearch_response


if __name__ == "__main__":
    hnair_raw_data()
    
