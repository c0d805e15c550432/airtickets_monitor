"""
航班搜索原始数据抓取 - 携程旅行(ctrip.com)
依赖：playwright (需安装: pip install playwright && playwright install chromium)
功能：输入出发地/目的地/日期，返回 FlightListSearch 接口的完整 JSON 响应
"""

from playwright.sync_api import sync_playwright
import json
import time
from datetime import datetime, date
from typing import Optional, Dict
from playwright.sync_api import expect

def select_flight_date(page, year, month, day):
    # 1. 格式化显示文本（去除前导零）
    year_display = f"{int(year)}年"
    month_display = f"{int(month)}月"
    day_display = str(int(day))

    # 2. 点击出发日期输入框，打开日历
    date_input = page.locator('input[aria-label="请选择日期"]').first
    date_input.click() 

    # 3. 等待日历弹窗出现（任意一个月历块可见即可）
    page.locator('.date-picker.date-picker-block').first.wait_for(
        state='visible', timeout=5000
    )

    # 4. 从所有日历块中筛选出目标年月所在的唯一容器
    target_month = page.locator('.date-picker.date-picker-block').filter(
        has=page.locator(f'.date-m:has-text("{int(year)}年{int(month)}月")')
    ).first

    # 5. 如果目标月份未出现，循环切换月份（假设目标在未来）
    max_attempts = 12
    while target_month.count() == 0 and max_attempts > 0:
        next_btn = page.locator('.next-ico:not(.disable)').first
        if next_btn.count() == 0:
            raise Exception("无法找到可点击的下一月按钮")
        next_btn.click()
        # 等待月份标题更新（任一日历块的年月发生变化）
        page.locator('.date-m').first.wait_for(
            has_text=f"{int(year)}", timeout=3000
        )
        # 重新获取目标月份容器
        target_month = page.locator('.date-picker.date-picker-block').filter(
            has=page.locator(f'.date-m:has-text("{int(year)}年{int(month)}月")')
        ).first
        max_attempts -= 1

    if target_month.count() == 0:
        raise Exception(f"在{12 - max_attempts}次尝试后仍未找到{year_display}{month_display}")

    # 6. 在目标月份容器内点击具体日期
    day_cell = target_month.locator(
        f'xpath=.//div[contains(@class, "date-day") and not(contains(@class, "date-disabled"))]'
        f'//span[@class="date-d" and contains(text(), "{day_display}")]/..'
    )

    expect(day_cell.first).to_be_enabled(timeout=3000)
    day_cell.first.click()

    # 7. 验证输入框的值已更新（可选）
    expect(date_input).to_have_value(f"{int(year)}-{int(month):02d}-{int(day):02d}")

def ctrip_raw_data() -> Optional[Dict]:
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
        

# 1. 修改容器结构，初始值设为空字典
        capture_container = {"response": None}

        def on_response(response):
            # 2. 检查具体的 API 路径
            if "batchSearch" in response.url and response.request.method == "POST":
                if response.status == 200:
                    try:
                        # 3. 必须通过键值对修改，才能影响到外部作用域
                        res_body = response.json()
                        if res_body:
                            capture_container["response"] = res_body
                            # print(f"成功捕获 API 数据，长度: {len(str(res_body))}")
                    except Exception as e:
                        print(f"解析 JSON 失败: {e}")

        context.on("response", on_response)
        page = context.new_page()

        # 1. 访问携程首页
        print("正在加载航班搜索页...")
        page.goto("https://flights.ctrip.com/online/channel", wait_until="networkidle", timeout=10000)
        time.sleep(1)  # 等待页面稳定

        #1.5 点击单程
        page.get_by_text("单程").wait_for(state='visible', timeout=5000)
        page.get_by_text("单程").click()

        # 2. 填写出发地
        print(f"出发地: {config["depart"]}")
        page.locator('input[name="owDCity"]').first.fill(config["depart"])
        time.sleep(0.1)
        # 等待下拉框出现并选择第一个（通常自动补全）
        page.locator('.address.active-poi').first.click(timeout=5000)
        time.sleep(1)

        # 3. 填写目的地
        print(f"目的地: {config["arrive"]}")
        page.locator('input[name="owACity"]').first.fill(config["arrive"])
        time.sleep(0.1)
        page.locator('.address.active-poi').first.click(timeout=5000)
        time.sleep(1)

        # 4. 选择出发日期
        print(f"出发日期: {config["year"]+config["month"]+config["day"]}")
        select_flight_date(page, config["year"], config["month"], config["day"])

        # 5. 点击搜索按钮
        print("正在提交搜索...")
        page.locator('button[type="submit"]').first.click()

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
                    #可能出现登录页面
                    # if batchSearch_response.get("data").get("needUserLogin"): # 触发登录并刷新后会返回一次异常数据，跳过
                    #     continue
                    if batchSearch_response.get("data").get("context").get("searchId") == "null-null":
                        print("未查询到数据，请检查日期及出发/目的地或切换数据源")
                    elif batchSearch_response.get("data").get("context").get("searchId") == '':
                        # searchId为空字符串说明遇到人机验证，没有返回实际数据
                        print("请求被阻拦，可能遇到人机验证,请在浏览器界面手动处理或切换数据源...")
                        capture_container["response"] = None

                    elif "flightItineraryList" in batchSearch_response["data"]:
                        # searchId有内容表面返回了数据
                        print("获取到有效数据！")
                        if config["dump_raw_data"]:
                            # 保存到文件
                            filename = f"./raw_data/ctrip_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                            with open(filename, "w", encoding="utf-8") as f:
                                json.dump(batchSearch_response, f, indent=2, ensure_ascii=False)
                            print("数据已保存到", filename)
                        break
                    else:
                        raise ValueError("未知错误")
                except Exception as e:
                    print(batchSearch_response)
                    print("数据异常！",e)       

            time.sleep(0.5) # 循环检测间隔

        else:
            print("未捕获到目标数据。")

        
        browser.close()
        
        return batchSearch_response


if __name__ == "__main__":
    ctrip_raw_data()
    
