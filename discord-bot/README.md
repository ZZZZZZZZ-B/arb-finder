# Mac 截图答题 GUI

一个 Python 编写的 macOS 答题助手：框选屏幕上的题目区域，按 **⌥ Space（Option + 空格）**，程序通过 OpenRouter Decisions API 判断截图中的命题，并在浮窗显示 **True / False**。

无需手动保存截图或上传到 Discord，也不需要 Discord Token 或频道 ID。只在快捷键或按钮触发时截图，不持续录屏。无法判断或请求失败时会提示失败，不会猜测。

## 功能

- 拖动框选题目区域，并记住选区位置。
- 全局快捷键 **⌥ Space**，也可点击“立即判断”。
- 置顶窗口显示 True / False，截图前暂时隐藏自身窗口。
- 请求期间防止重复触发。
- 暂停/恢复、统计和退出按钮。
- SQLite 持久化记录请求次数、平均 API 耗时及累计已知费用。
- 截图仅在内存中处理，不保存到磁盘。

## 安装

需要 **macOS 13 或更新版本**（当前 Qt 依赖要求）和 **Python 3.10 或更新版本**。

从仓库根目录进入助手目录并安装依赖：

```bash
cd discord-bot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-mac.txt
```

目录沿用早期的 `discord-bot` 名称；GUI 入口是 `mac_assistant.py`，不是 `discord_bot.py`。后者目前提供 GUI 复用的 API 和统计逻辑，以及可选的旧 Discord 集成。

## 配置与启动

在本机设置 OpenRouter API Key，不要把实际密钥写入代码或提交：

```bash
export OPENROUTER_API_KEY='YOUR_OPENROUTER_API_KEY'
export OPENROUTER_MODEL='openai/gpt-6-luna-decisions'
python mac_assistant.py
```

`OPENROUTER_API_KEY` 必填。可选配置：

| 环境变量 | 默认值 | 用途 |
| --- | --- | --- |
| `OPENROUTER_MODEL` | `openai/gpt-6-luna-decisions` | 支持图片输入的 Decisions 模型 |
| `MAC_STATS_DB` | `output/mac_stats.sqlite3` | SQLite 统计数据库路径 |

程序直接读取环境变量，不会自动加载 `.env`。修改密钥或模型后需要重启程序。

## macOS 权限

在 **系统设置 → 隐私与安全** 中，为运行 Python 的终端或应用授予：

- **屏幕与系统音频录制 / 屏幕录制**：用于获取选区画面；程序不采集音频。
- **辅助功能 / 输入监控**：全局快捷键可能需要这些权限。

权限修改后可能需要重启终端及程序。若快捷键不可用，可以先使用“立即判断”按钮；截图仍需要屏幕录制权限。

## 使用流程

1. 启动程序，将鼠标放在题目所在的显示器。
2. 点击 **“框选区域（鼠标所在屏幕）”**，拖动选中题目；按 Esc 可取消。
3. 尽量只框选完整题目文字，不包含私人内容，通常无需包含 True/False 按钮。
4. 按 **⌥ Space**，等待浮窗显示答案。
5. 题目更新后，再按快捷键判断下一题。

屏幕布局或分辨率变化后应重新框选。如果截图为空或答案不符，请检查权限、选区以及图片文字是否清晰。快捷键若与其他软件冲突，可以使用按钮。

点击“暂停 / 恢复”可以停止或恢复新的截图请求；已发出的请求不会取消。退出程序时，正在执行的网络请求可能会等待超时后才结束。

## 历史统计

点击窗口中的 **“统计”** 按钮查看：

```text
历史 API 统计
总次数：10（失败：0）
平均耗时：1.250 秒
累计已知费用：$0.0010000 USD
```

示例数字仅用于展示。总次数包含失败及无法判断的请求；平均耗时计算 API 调用时间，不含截图、图片编码和结果显示时间。累计已知费用来自 OpenRouter `usage.cost`，单位为美元；未返回的费用保存为 NULL，不代表免费。

数据库保存请求时间、耗时、费用和失败状态，重启后保留。不会保存截图、题目正文或密钥。历史 Discord 统计不会自动并入 GUI 数据库。

选区坐标及显示器名称保存在本地 `output/mac_region.json`。默认路径相对于启动时的工作目录，建议始终从助手目录运行。`output/` 已被 Git 忽略，仓库不包含数据库或选区配置。

## API 与隐私

使用 `https://openrouter.ai/api/alpha/decisions`，发送多模态 `state` 和 `choice` 问题，读取 `answers.is_true.choice`。

**按快捷键或点击“立即判断”后，选区截图会发送到 OpenRouter 及模型提供商，调用可能产生费用。** 不保存截图到本地不等于图片不会离开电脑；请避免框入聊天记录、账号信息、密码等私人内容。

仓库忽略环境文件、数据库、日志、截图、虚拟环境及本地工具元数据。不要提交实际密钥；泄露的密钥应撤销并重新生成。模型判断不保证正确，不应作为高风险决策的唯一依据。

## 测试

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

单元测试使用模拟 API，不消耗模型额度。实际 macOS 权限、全局快捷键、Retina 和多显示器截图需要在桌面环境中验证。
