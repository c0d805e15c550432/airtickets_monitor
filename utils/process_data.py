import json
import re
from pathlib import Path

from bs4 import BeautifulSoup


from utils.get_data_ly import ly_raw_data
from utils.get_data_ctrip import ctrip_raw_data
from utils.get_data_fliggy import fliggy_raw_data
from utils.get_data_csair import csair_raw_data
from utils.get_data_ceair import ceair_raw_data
from utils.get_data_hnair import hnair_raw_data

# 获取当前文件所在目录的绝对路径
current_dir = Path(__file__).parent  # -> .../airtickets_monitor/modules

# 获取项目根目录（上一级）
project_root = current_dir.parent

def ly():
    '''
    处理从同程旅行（ly.com）爬取的原始数据，输出包含航班号和票价的列表[{'flightNo': "航班号", 'price': “当前票价”}，……]
    '''
    # 1. 处理json数据
    # with open(f"{project_root}\\raw_data\\ly_20260215_224732.json", "r", encoding="utf-8") as f:
    #     flight_list = json.load(f).get("body", {}).get("FlightInfoSimpleList", [])
    data_tuple = ly_raw_data()
    if data_tuple[0]:
        flight_list = data_tuple[0].get("body", {}).get("FlightInfoSimpleList", []) #提取出包含航班详细信息的FlightInfoSimpleList列表
        processed_data = list(map(lambda x: {"flightNo": x.get("flightNo"), "price": x.get("lcp")}, flight_list)) # 从详细信息中提取出航班号及票价信息
    else:
        processed_data = []
    #2. 处理HTML数据
    # with open(f"{project_root}\\raw_data\\ly_20260215_224732.html", "r", encoding="utf-8") as f:
    #     html_content = f.read()
    html_content = data_tuple[1]["response"]
    soup = BeautifulSoup(html_content, 'html.parser')

    # 1. 找到所有的航班列表条目
    flight_items = soup.find_all('div', class_='flight-item')

    for item in flight_items:
        # 2. 提取航班号 (位于 class="flight-item-name" 的 p 标签中)
        # 使用 strip() 去掉多余换行和空格，并用正则只保留字母数字部分
        name_text = item.find('p', class_='flight-item-name').get_text(strip=True)
        # 提取如 "中国国际航空CA1292" 中的 "CA1292"
        flight_no_match = re.search(r'[A-Z0-9]{5,6}', name_text)
        flight_no = flight_no_match.group(0) if flight_no_match else name_text

        # 3. 提取价格 (位于 class="head-prices" 下的 em 标签)
        price_text = item.find('div', class_='head-prices').find('em').get_text(strip=True)
        # 去掉 ¥ 符号，转为整数
        price = int(price_text.replace('¥', ''))

        processed_data.append({
            "flightNo": flight_no,
            "price": price
        })
    return list(processed_data)

def ctrip():
    '''
    处理从携程旅行（ctrip.com）爬取的原始数据，输出包含航班号和票价的列表[{'flightNo': "航班号", 'price': “当前票价”}，……]
    '''
    # with open(f"{project_root}\\raw_data\\flight_raw_response.json", "r", encoding="utf-8") as f:
    #     raw_data = json.load(f)
    raw_data = ctrip_raw_data()
    flight_list = filter(lambda x: len(x.get("flightSegments")[0].get("flightList")) == 1, raw_data.get("data", {}).get("flightItineraryList", []))
    processed_data = list(map(lambda x: {"flightNo": x.get("flightSegments")[0].get("flightList")[0].get("flightNo"), "price": x.get("priceList")[0].get("adultPrice")}, flight_list))
    return list(processed_data)

def fliggy():
    '''
    处理从飞猪（fliggy.com）爬取的原始数据，输出包含航班号和票价的列表[{'flightNo': "航班号", 'price': “当前票价”}，……]
    '''
    # with open(f"{project_root}\\raw_data\\fliggy_20260526_195645.json", "r", encoding="utf-8") as f:
    #     flight_list = json.load(f).get("data", {}).get("flight", [])
    flight_list = fliggy_raw_data().get("data", {}).get("flight", [])
    processed_data = list(map(lambda x: {"flightNo": x.get("flightNo"), "price": x.get("cabin").get("price")}, flight_list))
    return list(processed_data)

def csair():
    '''
    处理从中国南方航空（csair.com）爬取的原始数据，输出包含航班号和票价的列表[{'flightNo': "航班号", 'price': “当前票价”}，……]
    '''
    # with open(f"{project_root}\\raw_data\\csair_query.json", "r", encoding="utf-8") as f:
    #     data = json.load(f)
    data = csair_raw_data()
    flight_list = data.get("data", {}).get("segment", [])[0].get("dateFlight", {}).get("flight", [])
    # print(flight_list)
    processed_data = list(map(lambda x: {"flightNo": x.get("flightNo"), "price": x.get("cabin")[0].get("gbAdultPrice")}, flight_list))
    return list(processed_data)

def ceair():
    '''
    处理从中国东方航空（ceair.com）爬取的原始数据，输出包含航班号和票价的列表[{'flightNo': "航班号", 'price': “当前票价”}，……]
    '''
    # with open(f"{project_root}\\raw_data\\ceair.json", "r", encoding="utf-8") as f:
    #     data = json.load(f)
    data = ceair_raw_data()
    print(str(data)[:1000]) # 打印部分原始数据以供调试
    flight_list = filter(lambda x: len(x.get("flightInfos")[0].get("flightSegments", [])) == 1, data.get("data", {}).get("flightItems", []))
    processed_data = list(map(lambda x: {"flightNo": x.get("flightInfos")[0].get("flightSegments")[0].get("airlineCode") + x.get("flightInfos")[0].get("flightSegments")[0].get("flightNo"), "price": x.get("flightInfos")[0].get("flightSort").get("price")}, flight_list))
    return list(processed_data)

def hnair():
    '''
    处理从海南航空（hnair.com）爬取的原始数据，输出包含航班号和票价的列表[{'flightNo': "航班号", 'price': “当前票价”}，……]
    '''
    # with open(f"{project_root}\\raw_data\\hnair.json", "r", encoding="utf-8") as f:
    #     data = json.load(f)
    data = hnair_raw_data()
    flight_list = data.get("FlightSearchResults", {}).get("Flights", [])[0].get("Flight", [])
    processed_data = list(map(lambda x: {"flightNo": x.get("FlightDetails")[0].get("Code", "") + x.get("FlightDetails")[0].get("FlightLeg", [])[0].get("FlightNumber", ""), "price": x.get("Price", {}).get("FareInfos")[0].get("FareInfo", "")[0].get("FareInfo", "")[0].get("Fare", "").get("BaseAmount", "")}, flight_list))
    return list(processed_data)

if __name__ == "__main__":
    # data_1 = ly()
    # print(data_1)
    # print(len(data_1))
    
    # data_2 = fliggy()
    # print(data_2)
    # print(len(data_2))

    # data_3 = ctrip()
    # print(data_3)
    # print(len(data_3))

    # data_4 = csair()
    # print(data_4)
    # print(len(data_4))

    # data_5 = ceair()
    # print(data_5)
    # print(len(data_5))

    data_6 = hnair()
    print(data_6)
    print(len(data_6))
