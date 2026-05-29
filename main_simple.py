import pandas as pd
from utils import process_data
from datetime import datetime
import time
import os

def save_flights_to_excel(data_list, file_name='./outputs/flights.xlsx'):
    # 1. 准备数据
    # 将 [{'flightNo': 'CZ6903', 'price': 1990}, ...] 转为字典
    # 格式为：{'时间': '2026-xx-xx', 'CZ6903': 1990, 'CA1902': 1930, ...}
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    row_data = {'采集时间': current_time}
    for item in data_list:
        row_data[item['flightNo']] = item['price']
    
    # 转换为 DataFrame
    df_new = pd.DataFrame([row_data])

    # 2. 写入或追加
    if not os.path.exists(file_name):
        # 如果文件不存在，直接创建，'采集时间'会自动排在第一列
        df_new.to_excel(file_name, index=False)
        print(f"成功创建新文件: {file_name}")
    else:
        # 如果文件已存在，读取旧数据，追加新行
        # 使用 mode='a' (append) 需要配合 openpyxl，这里用更通用的“读写覆盖”法
        df_old = pd.read_excel(file_name)
        # 合并新旧数据（注意：如果新抓取的航班号之前没出现过，会自动在后面增加新列）
        df_final = pd.concat([df_old, df_new], ignore_index=True)
        df_final.to_excel(file_name, index=False)
        print("数据已成功追加")

while True:
    try:
        data = process_data.ctrip()
        print(f"成功采集到 {len(data)} 条数据")
    except Exception as e:
        print(f"采集数据时发生错误: {e}")
        data = process_data.ly() # 备用数据源
        print(f"成功采集到 {len(data)} 条数据（备用数据源）")
    except Exception as e:
        print(f"备用数据源采集时发生错误: {e}")
        data = []
    save_flights_to_excel(data)
    print("等待下一次采集...")
    time.sleep(7200) # 每2小时执行一次

# save_flights_to_excel(process_data.ctrip())