import json
import os
import time
import platform
import subprocess
import config
from model import info_finder


def monitor_folder(all_config):
    File_Config = all_config['File_Config']
    WX_Applet_Path = File_Config['WX_Applet_Path']

    before = dict([(f, None) for f in os.listdir(WX_Applet_Path)])
    print(before)

    while True:
        time.sleep(File_Config['Sleep_Time'])  # 间隔休眠再检查一次
        after = dict([(f, None) for f in os.listdir(WX_Applet_Path)])
        added = [f for f in after if not f in before]
        if added:
            print("New folder(s) created:", ", ".join(added))
            for son_folder in added:
                print("等待程序下载...")
                time.sleep(File_Config['Sleep_Time'])   # 等待程序下载
                Applet_Packet_Save_Folder = unpacket(WX_Applet_Path, son_folder, File_Config)
                info_finder.run_info_finder(Applet_Packet_Save_Folder, all_config)
        else:
            print(before)
        before = after


def build_output_folder(wx_secret, File_Config):
    current_path = os.getcwd()
    target = os.path.join(current_path, File_Config['Applet_Packet_Save_Path'], wx_secret)
    os.makedirs(target, exist_ok=True)
    return target


def rename_with_appname(Applet_Packet_Save_Folder, wx_secret, File_Config):
    time.sleep(1)
    applet_packet_config_path = os.path.join(Applet_Packet_Save_Folder, 'app.json')
    try:
        with open(applet_packet_config_path, 'r', encoding='utf-8') as f:
            app_name = json.loads(f.read())['window']['navigationBarTitleText']
    except Exception:
        app_name = ''
    new_folder = os.path.join(
        os.getcwd(),
        File_Config['Applet_Packet_Save_Path'],
        f"{app_name}_{wx_secret}_{time.strftime('%Y_%m_%d_%H_%M_%S')}"
    )
    os.rename(Applet_Packet_Save_Folder, new_folder)
    return new_folder


def _unveilr_unpacket(mon_folder='', son_folder='', File_Config=None):
    print('开始解包和反编译（unveilr）')
    wx_secret = son_folder
    Applet_Packet_Save_Folder = build_output_folder(wx_secret, File_Config)

    cmd = (
        f"cd {File_Config['Unveilr_Path']};./{File_Config['Unveilr_Program_Name']} "
        f"wx \"{os.path.join(mon_folder, son_folder)}\" "
        f"-d {File_Config['Unveilr_Depth']} "
        f"-o \"{Applet_Packet_Save_Folder}\" "
        f"--clear-output"
    )
    if platform.system() == 'Windows':
        cmd = 'powershell;' + cmd

    subprocess.run(cmd, shell=True, encoding='utf-8', check=True)
    new_folder = rename_with_appname(Applet_Packet_Save_Folder, wx_secret, File_Config)
    print(f'解包和反编译搞定：{new_folder}')
    return new_folder


def _wxapkg_unpacket(mon_folder='', son_folder='', File_Config=None):
    print('开始解包和反编译（wxapkg）')
    wx_secret = son_folder
    Applet_Packet_Save_Folder = build_output_folder(wx_secret, File_Config)
    source_root = os.path.join(mon_folder, son_folder)
    disable_beautify = File_Config.get('Wxapkg_Disable_Beautify', False)

    cmd = (
        f"cd {File_Config['Wxapkg_Path']};./{File_Config['Wxapkg_Program_Name']} unpack "
        f"-o \"{Applet_Packet_Save_Folder}\" "
        f"-r \"{source_root}\" "
        f"-n {File_Config.get('Wxapkg_Threads', 30)}"
    )
    if disable_beautify:
        cmd += " --disable-beautify"
    if platform.system() == 'Windows':
        cmd = 'powershell;' + cmd

    subprocess.run(cmd, shell=True, encoding='utf-8', check=True)
    new_folder = rename_with_appname(Applet_Packet_Save_Folder, wx_secret, File_Config)
    print(f'解包和反编译搞定：{new_folder}')
    return new_folder


def unpacket(mon_folder='', son_folder='', File_Config=None):
    method = (File_Config.get('Unpack_Method', 'wxapkg') or 'wxapkg').lower()
    if method == 'unveilr':
        return _unveilr_unpacket(mon_folder, son_folder, File_Config)
    return _wxapkg_unpacket(mon_folder, son_folder, File_Config)


def unveilr_unpacket(mon_folder='', son_folder='', File_Config=None):
    # 兼容旧调用，使用新的调度逻辑
    return unpacket(mon_folder, son_folder, File_Config)


if __name__ == '__main__':
    config_yaml = r'./config.yaml'
    all_Config = config.load_config(config_yaml)
    monitor_folder(all_Config)
