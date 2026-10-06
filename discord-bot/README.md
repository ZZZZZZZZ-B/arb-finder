# Discord Screenshot Decisions Bot

监听指定 Discord 频道中的新图片附件，通过 OpenRouter Decisions API 判断截图中的命题，回复 `True` 或 `False`。无法判断或 API 出错时会提示失败，不会猜测。每条消息处理第一张图片，最大 10 MB；忽略机器人消息和历史消息。

## 安装

需要 Python 3.10 或更新版本。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Discord 设置

1. 在 Discord Developer Portal 创建应用及 Bot，开启 **Message Content Intent**。
2. 使用 `bot` 和 `applications.commands` scopes 邀请到服务器。
3. 给目标频道授予 View Channel、Send Messages、Read Message History 权限；用户需要 Use Application Commands 权限。
4. 开启 Discord 开发者模式，复制目标频道 ID。

## 配置与启动

在本机设置环境变量，不要提交实际密钥或频道 ID：

```bash
export DISCORD_TOKEN='YOUR_DISCORD_BOT_TOKEN'
export OPENROUTER_API_KEY='YOUR_OPENROUTER_API_KEY'
export DISCORD_CHANNEL_ID='YOUR_CHANNEL_ID'
export OPENROUTER_MODEL='openai/gpt-6-luna-decisions'
python discord_bot.py
```

`DISCORD_CHANNEL_ID` 必填，机器人只处理该频道的图片消息。可选变量：

- `DISCORD_STATS_DB`：SQLite 路径，默认 `output/discord_stats.sqlite3`。
- `OPENROUTER_SITE_URL`、`OPENROUTER_SITE_NAME`：可选 OpenRouter 应用标识。
- `LOG_LEVEL`：默认 `INFO`。

脚本直接读取环境变量，不会自动加载 `.env`。

请求接口为 `https://openrouter.ai/api/alpha/decisions`，使用多模态 `state` 和 `choice` 问题，读取 `answers.is_true.choice`。模型必须支持 Decisions 和图片输入。图片及消息文字会发送给 OpenRouter/模型提供商；每次调用可能产生费用。

## `/stats`

启动时自动同步到目标频道所在服务器；只在目标频道可使用，回复仅对执行者可见。

```text
历史 API 统计
总次数：10（失败：0）
平均耗时：1.250 秒
累计已知费用：$0.0010000 USD
```

示例数字仅用于展示。总次数包含失败和无法判断的请求，平均时间计算 API 调用耗时，不含图片下载和 Discord 回复。累计已知费用来自 `usage.cost`；缺失费用保存为 NULL，不代表免费。

SQLite 保存时间、耗时、费用和失败状态，重启后保留。不会保存截图、问题正文或凭据。仓库不包含任何历史数据库。

## 测试

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

测试使用模拟 API，不消耗模型额度。

## 安全

仓库忽略环境文件、数据库、日志、截图、虚拟环境及本地工具元数据。不要在代码或提交中写入 Token。泄露的密钥应立即撤销并重新生成。判断结果不保证正确，不应作为高风险决策的唯一依据。
