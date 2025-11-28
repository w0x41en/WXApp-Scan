import argparse
import os
import sys
from model import unwxapkg, config, infoFinder

EXAMPLE_USAGE = """
示例:
  扫描一个已解包的文件夹: python main.py --mode sf --folder-path .\\app_code\\demo --config-file config\\config.yaml
  直接解包并扫描 wxapkg:   python main.py --mode sp --folder-path \"D:\\\\WeChat Files\\\\Applet\\\\wx123...\" --config-file config\\config.yaml
  持续监控默认目录:         python main.py --mode mf --config-file config\\config.yaml
"""


def fail(msg, code=1):
    print(msg)
    sys.exit(code)


def ensure_path_exists(path, hint):
    if not path or not os.path.exists(path):
        fail(f"{hint} 路径不存在: {path}")
    return os.path.abspath(path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="folder-infoFinder: 解包 (可选) 并扫描微信小程序代码中的敏感信息。",
        epilog=EXAMPLE_USAGE,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("--mode", required=True, choices=["sp", "sf", "mf"], help="选择启动模式：sp 解包+扫描; sf 扫描已有代码目录; mf 监控小程序更新包目录。")
    parser.add_argument("--config-file", default=r'./config/config.yaml', help="指定配置文件路径 (默认 ./config/config.yaml)")
    parser.add_argument("--wxid", help="微信小程序的 AES secret key（如果需要解密）")
    parser.add_argument("--folder-path", help="指定的包或文件夹路径（sp/sf 模式必填）")

    args = parser.parse_args()

    config_path = ensure_path_exists(args.config_file, "配置文件")
    all_config = config.load_config(config_yaml_path=config_path)

    if args.mode in ('sp', 'sf') and not args.folder_path:
        fail("请用 --folder-path 指定文件或文件夹。示例: --folder-path D:\\WeChat Files\\Applet\\wx1234567890")

    if args.mode == 'sp':
        target_path = ensure_path_exists(args.folder_path, "待解包的 wxapkg 或目录")
        mon_folder = os.path.dirname(target_path)
        son_folder = os.path.basename(target_path)
        Applet_Packet_Save_Folder = unwxapkg.unpacket(mon_folder, son_folder, all_config['File_Config'])
        infoFinder.infoFinder(Applet_Packet_Save_Folder, all_config)
    elif args.mode == 'mf':
        unwxapkg.monitor_folder(all_config)
    elif args.mode == 'sf':
        target_path = ensure_path_exists(args.folder_path, "待扫描的文件夹")
        infoFinder.infoFinder(target_path, all_config)
