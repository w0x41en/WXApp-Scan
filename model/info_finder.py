import json
import os
import queue
import re
import threading
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Pattern, Set, Tuple

import pandas as pd
import yaml

from model import active_request


@dataclass(frozen=True)
class RuleSet:
    compiled: Dict[str, Pattern]
    additional_rule_names: Set[str]


def iter_target_files(target_folder: str, file_scan_config: dict) -> Iterable[str]:
    for current_path, _, files_name in os.walk(target_folder):
        for file in files_name or []:
            if is_allowed_suffix(file, file_scan_config):
                yield os.path.join(current_path, file)


def scan_files(file_scan_config: dict, rule_set: RuleSet, target_folder: str) -> Dict[str, List[str]]:
    # 创建基本变量
    match_results: Dict[str, List[str]] = {name: [] for name in rule_set.compiled}

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
                for reg_rule_name, regex in rule_set.compiled.items():
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
        match_results[reg_rule_name] = deduplicate_hits(match_results[reg_rule_name], file_scan_config)
    return match_results


def deduplicate_hits(raw_hits: List, file_scan_config: dict) -> List[str]:
    blacklist = {'http', 'https'}
    cleaned: List[str] = []
    for hit in raw_hits:
        normalized = normalize_hit(hit, blacklist)
        if normalized not in cleaned and is_allowed_suffix(normalized, file_scan_config):
            cleaned.append(normalized)
    return cleaned


def normalize_hit(hit, blacklist: Set[str]) -> str:
    if isinstance(hit, str):
        return hit
    hit_list = list(hit)
    hit_list = ['' if part in blacklist else part for part in hit_list]
    return max(hit_list, key=len)


def is_allowed_suffix(filename: str, file_scan_config: dict) -> bool:
    filename_split = filename.split('.')
    if file_scan_config['Black_Suffix_list']['active']:
        return not (len(filename_split) > 1 and filename_split[-1] in file_scan_config['Black_Suffix_list']['suffix_list'])
    if file_scan_config['White_Suffix_list']['active']:
        return len(filename_split) > 1 and filename_split[-1] in file_scan_config['White_Suffix_list']['suffix_list']
    return True


def write2excel(match_results: Dict[str, List[str]], Excel_Folder: str, target_folder: Optional[str], additional_rule_names: Set[str]):
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

    sanitized_results = sanitize_results(match_results)
    df = build_dataframe_for_excel(sanitized_results, additional_rule_names)

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


def run_info_finder(target_folder='', all_config=None):
    rule_set = load_rules(all_config['Regex_Config'])
    match_results = scan_files(all_config['File_Config'], rule_set, target_folder)
    write2excel(match_results, all_config['File_Config']['Excel_Folder'], target_folder, rule_set.additional_rule_names)
    if all_config['Request_Config']['request_active']:
        active_request.scan_active(match_results['Url_regex'], match_results['Uri_regex'], all_config['Request_Config'])
    return


def load_rules(regex_config: dict) -> RuleSet:
    """
    Build and compile regex rules from base and additional sources.
    """
    patterns, additional_names = collect_rule_patterns(regex_config)
    compiled = {name: re.compile(pattern) for name, pattern in patterns.items()}
    return RuleSet(compiled=compiled, additional_rule_names=set(additional_names))


def collect_rule_patterns(regex_config: dict) -> Tuple[Dict[str, str], List[str]]:
    base_rules: Dict[str, str] = {}
    additional_rules: List[dict] = []
    additional_names: List[str] = []

    for name, pattern in regex_config.items():
        if name in ('Additional_Secret_Rules', 'Additional_Secret_Rules_File'):
            continue
        base_rules[name] = pattern

    additional_rules.extend(regex_config.get('Additional_Secret_Rules', []) or [])
    rules_file = regex_config.get('Additional_Secret_Rules_File')
    if rules_file and os.path.exists(rules_file):
        try:
            with open(rules_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict) and data.get('rules'):
                additional_rules.extend(data['rules'])
        except Exception as e:
            print(f"加载外部规则文件失败 {rules_file}: {e}")

    for rule in additional_rules:
        if not isinstance(rule, dict) or not rule.get('enabled', True):
            continue
        pattern = rule.get('pattern')
        rule_id = rule.get('id') or f"rule_{len(base_rules)}"
        if pattern:
            base_rules[rule_id] = pattern
            additional_names.append(rule_id)

    return base_rules, additional_names


def format_hit(hit):
    if isinstance(hit, (list, tuple)):
        return ' '.join(map(str, hit))
    return str(hit)


def build_dataframe_for_excel(match_results: Dict[str, List[str]], additional_rule_names: Set[str]):
    """
    Each regex rule is a column. All additional rules are merged into a single
    'Additional_Secret_Rules' column with rule names prefixed.
    """
    base_rule_names = [name for name in match_results.keys() if name not in additional_rule_names]

    additional_hits = []
    for name in additional_rule_names:
        for hit in match_results.get(name, []):
            additional_hits.append(f"[{name}] {format_hit(hit)}")

    max_rows = max(
        max((len(match_results[name]) for name in base_rule_names), default=0),
        len(additional_hits)
    )

    data = {}
    for name in base_rule_names:
        col = [format_hit(hit) for hit in match_results[name]]
        col.extend([''] * (max_rows - len(col)))
        data[name] = col

    if additional_rule_names:
        additional_hits.extend([''] * (max_rows - len(additional_hits)))
        data['Additional_Secret_Rules'] = additional_hits

    return pd.DataFrame(data)


if __name__ == "__main__":
    folder = r'./test_folder'
    run_info_finder(folder)
