# DouyinDanmakuForwarder 免安装版

## 普通用户需要安装什么

使用 `dist\DouyinDanmakuForwarder-final.zip` 时，电脑上不需要安装 Python、Node.js、PyInstaller 或浏览器插件。压缩包已经包含采集器运行所需的 Python 运行环境、签名脚本、MiniRacer 原生依赖和启动脚本。

普通用户只需要准备：

1. Windows 10/11 电脑。
2. 能访问抖音直播间和平台地址的网络。
3. 平台正在运行，例如 `http://www.yangqingci.com`。
4. 平台账号已绑定直播间，并且已经分配对应游戏权限。

## 使用压缩包

1. 解压整个 zip 包到任意目录。
2. 双击 `start-forwarder.bat`。
3. 在窗口中填写平台地址、用户名、密码。
4. 点击“登录”。
5. 登录后选择直播间和游戏。
6. 点击“开始采集”。

采集器会从平台自动读取直播间 ID、采集 token 和可用游戏，不需要手动填写 `Ingest Token`，也不需要填写两次直播间 ID。

配置会保存到同目录的 `platform_ingest.env`。这个文件只保存平台地址、登录 token、上次选择的直播间和游戏，不保存登录密码。退出登录会清空 token。

## 平台地址

平台地址填写根地址即可，不要填写 `/ingest`：

```ini
PLATFORM_URL=http://www.yangqingci.com
```

本地联调可以填写：

```ini
PLATFORM_URL=http://127.0.0.1:8080
```

## 游戏权限

可选游戏由平台账号权限决定。账号没有某个游戏权限时，采集器下拉框不会显示这个游戏。

常见游戏代码：

```text
danmaku_exam     弹幕答题/驾考
semantic_guess   语义猜词
idiom_chain      成语接龙
```

## 源码运行或开发调试

直接运行源码时需要安装：

1. Python 3.11 或 3.12。Python 3.13 也可以使用，但建议优先用 3.11/3.12。
2. pip。
3. 运行时依赖：

```powershell
python -m pip install -r requirements.txt
```

源码运行方式：

```powershell
python portable\forwarder_gui.py
```

命令行版本仍可使用 `platform_ingest.py` 和旧的 `INGEST_*` 环境变量，主要用于开发调试；普通用户建议使用图形界面登录版。

## 重新构建免安装包

重新打包时需要 PyInstaller。构建脚本会自动安装 `portable\requirements-build.txt` 里的构建依赖；如果自动安装失败，可以手动执行：

```powershell
python -m pip install -r requirements.txt -r portable\requirements-build.txt
```

然后执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\portable\build.ps1 -Version final
```

或双击：

```text
portable\build.bat
```

产物位置：

```text
dist\DouyinDanmakuForwarder-final.zip
```

构建脚本会校验签名依赖、证书文件、启动脚本和说明文档，并阻止真实 `platform_ingest.env` 被打进 zip。

## 常见问题

`401`：账号登录已失效，退出登录后重新登录。

`403 Douyin room mismatch`：平台绑定的直播间和采集器当前直播间不一致，刷新配置或到平台重新绑定直播间。

`404 Game not found`：游戏代码不存在、游戏被禁用，或当前账号没有这个游戏权限。

看不到弹幕：先确认抖音直播间正在直播，再看采集器日志。如果日志里有 `[ingest] post failed`，说明采集到了弹幕但转发到平台失败；如果没有 WebSocket 连接成功日志，优先检查直播间 ID 和网络。
