# WXApp Scan（小程序敏感信息扫描）

一个用于解包、扫描微信小程序代码并输出敏感信息报告的工具。支持监控微信默认存储目录，或对指定包/目录进行单次扫描，包含实时进度条、可选 URL 验活、Excel 报表输出。

## 功能亮点
- 解包方式可选：支持 `wxapkg` 与 `unveilr`，通过配置切换。
- 多线程正则扫描，进度条实时展示。
- 自动清洗非法字符，稳定导出 Excel。
- 可选 URL/URI 验活（关闭默认），支持黑/白名单。

## 快速开始
1. 安装依赖（示例）：
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install pandas pyyaml requests openpyxl urllib3
   ```
2. 配置 `config/config.yaml`：
   - `File_Config.Unpack_Method`: `wxapkg`（默认）或 `unveilr`
   - `Wxapkg_Path` / `Unveilr_Path`: 解包工具所在目录
   - `Regex_Config`: 正则规则（已内置域名、URL、AK、手机号等）
3. 运行命令：
   - 扫描已解包目录：`python main.py --mode sf --folder-path .\app_code\demo --config-file config\config.yaml`
   - 解包并扫描：`python main.py --mode sp --folder-path "D:\WeChat Files\Applet\wx123..." --config-file config\config.yaml`
   - 监控默认目录：`python main.py --mode mf --config-file config\config.yaml`

## 输出说明
- 扫描结果保存到 `output/<应用名_时间>.xlsx`，文件名优先取 `app.json` 的 `navigationBarTitleText`。
- 默认过滤图片/媒体后缀，可在 `Black_Suffix_list` / `White_Suffix_list` 调整。

## 常见问题
- Excel 写入报非法字符：已自动清洗；若仍有问题，检查自定义正则是否包含控制字符。
- 解包失败：确认 `Unpack_Method` 与对应二进制路径/权限；`--folder-path` 应指向小程序包目录（父目录 + 包名）。
