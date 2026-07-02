# DouyinDanmakuForwarder 免安装版

## 需要安装什么

### 普通用户使用压缩包

如果使用 `dist\DouyinDanmakuForwarder-final.zip`，电脑上不需要安装 Python、Node.js、PyInstaller、浏览器插件或 Chrome。压缩包里已经包含采集器运行所需的 Python 运行环境、签名脚本、MiniRacer 原生依赖和启动脚本。

普通用户只需要准备：

1. Windows 10/11 电脑。
2. 能访问抖音直播间和平台地址的网络。
3. 平台正在运行，并且 `/ingest` 地址可以访问，例如 `https://www.yangqingci.com/ingest`。
4. 平台直播间页面复制出来的 `Ingest Token`。
5. 抖音直播间 ID，例如直播间地址 `https://live.douyin.com/123456789` 里的 `123456789`。
6. 平台里已经给当前账号配置好目标游戏权限，并绑定正确的直播间 ID。

如果 Windows 安全软件拦截 `DouyinDanmakuForwarder.exe` 或网络访问，需要允许它运行和联网。

### 源码运行或开发调试

只有直接运行源码时才需要安装这些东西：

1. Python 3.11 或 3.12，Python 3.13 也可以使用，但建议优先用 3.11/3.12。
2. pip，通常会随 Python 一起安装。
3. 运行时依赖：

```powershell
python -m pip install -r requirements.txt
```

源码运行方式：

```powershell
python portable\forwarder_gui.py
```

也可以复制 `platform_ingest.env.example` 为 `platform_ingest.env` 后运行命令行版本：

```powershell
python platform_ingest.py
```

### 重新构建免安装包

重新打包时还需要 PyInstaller。构建脚本会自动安装 `portable\requirements-build.txt` 里的构建依赖；如果自动安装失败，可以手动执行：

```powershell
python -m pip install -r requirements.txt -r portable\requirements-build.txt
```

然后执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\portable\build.ps1 -Version final
```

或直接双击：

```text
portable\build.bat
```

## 使用压缩包

1. 解压整个 zip 包到任意目录。
2. 双击 `start-forwarder.bat`。
3. 在配置窗口填写平台接入地址、Ingest Token、抖音直播间 ID 和目标游戏。
4. 点击“保存配置”，再点击“开始采集”。

配置会保存到同目录的 `platform_ingest.env`。这个文件包含真实 token，不要发给别人，也不要提交到 git。

## 常用配置

```ini
INGEST_URL=https://www.yangqingci.com/ingest
INGEST_TOKEN=平台直播间页面复制的 ingest token
DOUYIN_LIVE_ID=抖音直播间ID
INGEST_ROOM_ID=抖音直播间ID
INGEST_GAME_CODE=danmaku_exam
```

游戏代码：

```text
danmaku_exam     驾考/弹幕答题
semantic_guess   语义猜词
idiom_chain      成语接龙
```

`INGEST_GAME_CODE` 必须明确填写，避免同一账号同时打开多个游戏页面时弹幕进错游戏。

## 构建最终包

在项目根目录双击：

```text
portable\build.bat
```

或者执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\portable\build.ps1 -Version 1.0.0
```

产物位置：

```text
dist\DouyinDanmakuForwarder-1.0.0.zip
```

构建脚本会校验签名依赖、启动脚本、说明文档，并阻止真实 `platform_ingest.env` 被打进 zip。

## 常见问题

`401`：`INGEST_TOKEN` 填错，或不是当前平台用户的 ingest token。

`403 Douyin room mismatch`：`INGEST_ROOM_ID` 和平台后台绑定的直播间 ID 不一致。

`404 Game not found`：`INGEST_GAME_CODE` 填错，或平台里该游戏被禁用。

看不到弹幕：先确认抖音直播间正在直播，再看配置窗口日志。如果日志里有 `[ingest] post failed`，说明采集到了弹幕但转发到平台失败；如果没有 WebSocket 连接成功日志，优先检查直播间 ID 和网络。
