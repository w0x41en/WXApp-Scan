import re
import os
import queue
import threading
import pandas as pd
import time
import json
from model import active_request


def iter_target_files(target_folder, file_scan_config):
    for current_path, _, files_name in os.walk(target_folder):
        for file in files_name or []:
            if check_suffix(file, file_scan_config):
                yield os.path.join(current_path, file)


def start_scan(file_scan_config, regex_config, target_folder):
    # 创建基本变量
    compiled_regex = {name: re.compile(pattern) for name, pattern in regex_config.items()}
    match_results = {name: [] for name in compiled_regex}

    target_files = list(iter_target_files(target_folder, file_scan_config))
    total_files = len(target_files)
    if total_files == 0:
        return match_results

    task_queue = queue.Queue()
    num_threads = 20
    threads = []
    result_lock = threading.Lock()
    progress_lock = threading.Lock()
    processed_files = 0
    last_percent = -1
    bar_length = 30

    for file_path in target_files:
        task_queue.put(file_path)

    def worker():
        nonlocal processed_files, last_percent
        while True:
            try:
                file_path = task_queue.get(block=False)
            except queue.Empty:
                break
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    file_content = f.read()
                for reg_rule_name, regex in compiled_regex.items():
                    hits = regex.findall(file_content)
                    if hits:
                        with result_lock:
                            match_results[reg_rule_name].extend(hits)
            except Exception as e:
                print(f"Caught an exception when scanning {file_path}: {e}")
            finally:
                with progress_lock:
                    processed_files += 1
                    percent = int(processed_files * 100 / total_files)
                    if percent != last_percent or processed_files == total_files:
                        last_percent = percent
                        filled = int(bar_length * percent / 100)
                        bar = '#' * filled + '-' * (bar_length - filled)
                        print(f"\r[scan] |{bar}| {percent:3d}% ({processed_files}/{total_files})", end='', flush=True)
                task_queue.task_done()

    # 创建线程池
    for i in range(num_threads):
        t = threading.Thread(target=worker)
        t.start()
        threads.append(t)

    # 阻塞直到所有任务完成
    task_queue.join()

    # 等待所有线程完成
    for t in threads:
        t.join()

    print()  # 换行，避免进度条影响后续输出

    # 去重、过滤结果
    for reg_rule_name in match_results:
        match_results[reg_rule_name] = clear_list(match_results[reg_rule_name], file_scan_config)
    return match_results


def clear_list(list01, file_scan_config):
    black_list = ['http', 'https']
    tamp_list = []
    for i in list01:
        if not isinstance(i, str):  # 检测是否为str对象
            i = list(i)
            for j in range(len(i)):
                if i[j] in black_list:
                    i[j] = ''
            i = max(i, key=len)
        if i not in tamp_list and check_suffix(i, file_scan_config):
            tamp_list.append(i)
    return tamp_list


def check_suffix(filename, file_scan_config):
    filename_split = filename.split('.')
    if file_scan_config['Black_Suffix_list']['active']:
        if len(filename_split) > 1 and filename_split[-1] in file_scan_config['Black_Suffix_list']['suffix_list']:
            return False
        else:
            return True
    elif file_scan_config['White_Suffix_list']['active']:
        if len(filename_split) > 1 and filename_split[-1] in file_scan_config['White_Suffix_list']['suffix_list']:
            return True
        else:
            return False


def write2excel(match_results=None, Excel_Folder=None, target_folder=None):
    app_name = extract_app_name(target_folder, match_results)
    if app_name:
        excel_name = f"{app_name}_{time.strftime('%Y_%m_%d_%H_%M_%S')}.xlsx"
    else:
        excel_name = f"{time.strftime('%Y_%m_%d_%H_%M_%S')}.xlsx"

    # 文件路径参数
    current_directory = os.getcwd()
    excel_folder = os.path.join(current_directory, Excel_Folder)
    excel_file = os.path.join(excel_folder, excel_name)
    print(f'正在写入 {excel_file} 表格中')

    check_folder_exists(excel_folder)

    df = pd.DataFrame.from_dict(sanitize_results(match_results), orient='index').transpose()

    # 将数据存储到Excel表格中
    writer = pd.ExcelWriter(excel_file, engine='openpyxl')
    df.to_excel(writer, sheet_name='Sheet1', index=False)
    writer.book.save(excel_file)

    print(f'写入成功：{excel_file}')

    return


def check_folder_exists(folder_path=None):
    # 检测文件夹是否存在，如果不存在则创建
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
        print(f"已创建文件夹 {folder_path}")
    return


def extract_app_name(target_folder, match_results):
    """
    优先从 app.json 读取 navigationBarTitleText，其次使用匹配结果或目录名。
    """
    def safe_name(name):
        if not name:
            return ''
        # 去除文件名不合法字符
        return re.sub(r'[\\/:*?"<>|]', '', name).strip()

    # 1) app.json
    if target_folder:
        app_json_path = os.path.join(target_folder, 'app.json')
        if os.path.exists(app_json_path):
            try:
                with open(app_json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                window_conf = data.get('window', {}) if isinstance(data, dict) else {}
                nav_title = window_conf.get('navigationBarTitleText') or window_conf.get('defaultTitle')
                if nav_title:
                    return safe_name(nav_title)
            except Exception:
                pass
    # 2) 正则匹配结果
    if match_results and match_results.get('App_Name_regex'):
        return safe_name(match_results['App_Name_regex'][0])
    # 3) 目录名兜底
    if target_folder:
        return safe_name(os.path.basename(os.path.abspath(target_folder)))
    return ''


def sanitize_results(match_results):
    illegal_chars = re.compile(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]')

    def clean_item(item):
        if isinstance(item, str):
            return illegal_chars.sub('', item)
        if isinstance(item, (list, tuple)):
            return [clean_item(i) for i in item]
        return item

    return {k: clean_item(v) for k, v in match_results.items()}


def infoFinder(target_folder='', all_config=None):
    match_results = start_scan(all_config['File_Config'], all_config['Regex_Config'], target_folder)
    # for i in match_results:
    #     print(f'\033[0;32;40m{i}\033[0m: {match_results[i]}')
    write2excel(match_results, all_config['File_Config']['Excel_Folder'], target_folder)
    if all_config['Request_Config']['request_active']:
        active_request.scan_active(match_results['Url_regex'], match_results['Uri_regex'], all_config['Request_Config'])
    return


if __name__ == "__main__":
    folder = r'./test_folder'
    infoFinder(folder)
