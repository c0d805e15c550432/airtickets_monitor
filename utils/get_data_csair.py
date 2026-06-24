"""
航班搜索原始数据抓取 - 南方航空(csair.com)
依赖：playwright (需安装: pip install playwright && playwright install chromium)
功能：输入出发地/目的地/日期，返回 FlightListSearch 接口的完整 JSON 响应
"""

from playwright.sync_api import sync_playwright
import json
import time
from datetime import datetime
from typing import Optional, Dict
from playwright.sync_api import expect

def select_calendar_date(page, target_date: str):
    """
    在日历组件中选择指定日期，如果当前页不存在则自动翻页
    
    :param page: Playwright Page 对象
    :param target_date: 目标日期，格式必须为 'YYYY-MM-DD'，例如 '2026-08-15'
    """
    calendar = page.locator("#UI-calendar-unit")
    next_btn = calendar.locator("a.cld-btn.next")
    prev_btn = calendar.locator("a.cld-btn.prev")
    
    max_attempts = 24  # 最多翻页次数，防止遇到不可选日期导致死循环
    attempt = 0
    
    while attempt < max_attempts:
        attempt += 1
        
        # 1. 尝试直接定位目标日期 (利用 data-value 属性，这是最精准的)
        target_locator = calendar.locator(f'li.day-box[data-value="{target_date}"]')
        
        # 如果目标日期在当前 DOM 中可见
        if target_locator.is_visible():
            # 点击内部的 a 标签触发选择（更符合真实用户行为）
            target_locator.locator("a.cld-ceil").click()
            print(f"✅ 成功选择日期: {target_date}")
            return True
        
        # 2. 如果当前页没有目标日期，判断需要向前还是向后翻页
        # 获取当前面板中第一个日历天的 data-value 作为基准日期
        first_day_value = calendar.locator("li.day-box").first.get_attribute("data-value")
        
        if not first_day_value:
            raise Exception("❌ 无法获取当前日历的基准日期，页面结构可能发生变化")
            
        # 3. 比较日期字符串大小决定翻页方向
        # YYYY-MM-DD 格式的字符串支持直接进行大小比较，无需转换为 datetime 对象
        if target_date > first_day_value:
            next_btn.click()
        else:
            prev_btn.click()
            
        # 4. 翻页后，等待日历 DOM 刷新完成
        # 原理：等待刚才那个基准日期从面板中消失，说明月份已经切换
        try:
            page.locator(f'li.day-box[data-value="{first_day_value}"]').wait_for(state="hidden", timeout=3000)
        except:
            # 如果翻页动画较慢导致超时，可以稍微等待一下
            page.wait_for_timeout(500)
            
    raise Exception(f"❌ 翻页 {max_attempts} 次后仍未找到日期 {target_date}，请检查日期是否合法或已被禁用")



def csair_raw_data() -> Optional[Dict]:
    """
    获取航班搜索原始响应数据
    :return:           接口返回的 JSON 数据，失败返回 None
    """

    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.get("headless", True), args=['--disable-blink-features=AutomationControlled'])
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        # 定义全局变量存储数据
        data = {"response": None}

# 1. 修改容器结构，初始值设为空字典
        capture_container = {"response": None}

        def on_response(response):
            # 2. 检查具体的 API 路径
            if "direct/query" in response.url and response.request.method == "POST":
                if response.status == 200:
                    try:
                        # 3. 必须通过键值对修改，才能影响到外部作用域
                        res_body = response.json()
                        if res_body.get("success", False):
                            capture_container["response"] = res_body
                            print(f"✅ 成功捕获 API 数据，长度: {len(str(res_body))}")
                    except Exception as e:
                        print(f"⚠️ 解析 JSON 失败: {e}")

        context.on("response", on_response)
        page = context.new_page()

        # 1. 访问携程首页
        print("正在加载航班搜索页...")
        page.goto("https://www.csair.com/cn/index_new.shtml", wait_until="networkidle", timeout=10000)
        time.sleep(1)  # 等待页面稳定


        # 2. 填写出发地
        print(f"出发地: {config.get('depart')}")
        page.locator('input[name="fDepCity"]').first.type(config.get('depart'))  # 模拟真实输入，增加延迟
        time.sleep(1)
        page.keyboard.press("Enter")
        time.sleep(1)

        # 3. 填写目的地
        print(f"目的地: {config.get('arrive')}")
        page.locator('input[name="fArrCity"]').first.type(config.get('arrive'))
        time.sleep(1)
        page.keyboard.press("Enter")
        time.sleep(1)

        # 4. 选择出发日期
        date = f"{config.get('year')}-{config.get('month')}-{config.get('day')}"
        print(f"出发日期: {date}")
        select_calendar_date(page, date)
        time.sleep(1)

        # 5. 点击搜索按钮
        print("正在提交搜索...")
        page.locator("text=立即查询").first.click()

        # 6. 等待目标响应出现
        print("等待航班数据返回...")
        max_wait = 60 
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            # 精准判断：只有当 "response" 不为 None 时才跳出
            if capture_container["response"] is not None:                
                try:
                    
                    batchSearch_response = capture_container["response"]
                    if batchSearch_response.get("data").get("id") != '':
                        print("检测到有效数据！")
                        if config["dump_raw_data"]:
                            # 保存到文件
                            filename = f"./raw_data/csair_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                            with open(filename, "w", encoding="utf-8") as f:
                                json.dump(batchSearch_response, f, indent=2, ensure_ascii=False)
                            print("数据已保存到", filename)
                        break
                    else:
                        print("请求被阻拦，可能遇到人机验证")
                        capture_container["response"] = None
                except Exception as e:
                    print("数据异常！",e)
                
                
            time.sleep(0.5) # 缩短轮询间隔，提高响应速度
            
            # 检查是否有滑动验证码（携程常见情况）
            if page.locator("outerContainer-background-translucent").is_visible():
                print("🛑 发现滑块验证！请在浏览器界面手动处理...")
        else:
            print("❌ 达到最大等待时间，未捕获到目标数据。")

        # 5. 拿到数据后再关闭浏览器
        browser.close()
        
        return batchSearch_response


if __name__ == "__main__":
    # 示例：乌鲁木齐→北京，单程
    raw_data = csair_raw_data(
        depart="URC",
        arrive="BJS",
        date="2026-02-24",
        headless=False  # 设为 False 可观察浏览器操作
    )
    
    if raw_data:
        # 打印缩进后的 JSON（或保存到文件）
        #print(json.dumps(raw_data, indent=2, ensure_ascii=False))
        
        # 保存到文件
        filename = f"flight_raw_response_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, indent=2, ensure_ascii=False)
        print("数据已保存到", filename)