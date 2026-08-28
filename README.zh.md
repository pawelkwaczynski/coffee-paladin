<p align="center">
  <img src="branding/paladin.gif" alt="coffee-paladin - 项目吉祥物" width="220">
</p>
<p align="center"><em>Shield the Process, Sip the Coffee</em></p>

# coffee-paladin

**为 Apple Silicon Mac 打造的过热与电源保险丝，从一台笔记本到整个机群。**
它监测芯片温度、电池、风扇和供电状态，在机器把自己烤坏之前**冻结**繁重任务，
而不是任由它们跑到强制关机。

**要求：Apple Silicon（M1 或更新）与 macOS 14+。** 不需要 `sudo`，不需要内核扩展，
没有以 root 身份运行的守护进程。所有传感器数据都由普通用户进程读取。

> 这是精简版。完整文档（含测量数据、失败案例和设计取舍）见
> [英文 README](README.md)。

<p align="center">
  <img src="docs/screens/menu_zh.webp" alt="coffee-paladin 菜单栏（中文）" width="360">
</p>

---

## 为什么会有这个项目

一台 MacBook Pro M4 Pro 通宵渲染视频。早上：机身下方传出焦味，机器硬关机。
更糟的是事后翻日志时**没有任何东西可查**：没有内核崩溃记录，没有过热关机记录，
系统日志就在机器死掉的那一刻断掉了。温度曲线无从还原。

而在 2026 年丢一台 Mac 比以往任何时候都疼。今年七月我们询价时，
波兰租赁商给出的新 MacBook 等货期是 15 周以上，连老款 M1 都在售罄，标价还涨了。

这个项目就是对这两件事的回答：**在烤坏之前拦住它**，以及**万一出事，留下证据**。

---

## 它到底做什么

**1. 暂停，而不是杀死。** 芯片过热时，繁重进程收到 `SIGSTOP`：进程原地冻结，
内存不动，降温后收到 `SIGCONT` 从断点继续。暂停发生在两条指令之间，
因此不会损坏进程数据。这也不是什么奇技淫巧，macOS 自己整天这么干
（App Nap 对后台应用就这么做，每个调试器附加时都这么做），硬件也没有损耗。
实测：芯片 89.3 °C → 暂停 → **19 秒后 60.2 °C** → 恢复，计算毫无察觉。

**2. 找出真正的元凶。** 只按名字匹配的白名单永远有漏洞：一个自编译的 `b3core`
把机器推到 90 °C，因为它不在任何名单上。更隐蔽的情况：一个 Python 脚本
每秒派生上百个只活一秒的 `cadical` 求解器，每个子进程都短到跨不过阈值，
父进程自己几乎不占 CPU，合起来却把八个核心跑满。所以 guard 计算的是
**整棵进程子树的 CPU 占用**，那个 Python 进程显示为 **595%**，并在源头冻结它。

<p align="center">
  <img src="docs/screens/load_info.webp" alt="负载信息：谁在发热，谁在吃内存" width="420">
</p>

**3. 不只看温度，也看电源。** 用电池且电量降到 10% 时暂停长任务，插上电源才恢复，
一个跑 30 天的计算不该因为笔记本没电而半途夭折。另外：芯片超过 70 °C 而两个风扇
都报告 0 rpm 时发出告警，风扇卡死正是上面那股焦味的常见成因。

**4. 让 Mac 保持唤醒，但带保险丝。** 计时器（15 分钟到 12 小时）、无限期、
某个应用运行期间、下载期间，和 Amphetamine 一样齐全。区别在于**保险丝**：
所有模式**只在机器凉快时**持有唤醒锁。一旦 guard 因过热开始暂停任务，锁立即释放，
因为睡眠是最快的散热手段。背包里无条件保持唤醒，正是 MacBook 被烤坏的典型方式。

<p align="center">
  <img src="docs/screens/keep_awake.webp" alt="带热保险丝的保持唤醒模式" width="420">
</p>

**5. 自我校准，并且认识自己这台机器。** 首次运行时测量这台机器的实际情况
（有没有风扇、多少核心、芯片型号）并据此选择阈值；无风扇的 Mac 得到更低的阈值
和更长的允许暂停时间，手动设置的阈值永远不会被覆盖。等历史数据攒够之后，`heat --profile` 会读取这台机器
自己的测量记录，告诉你它真实的边界在哪里：空闲温度、持续负载下的平台温度、
风扇启动温度、macOS 是否被迫降过频。如果现有阈值不适合这台机器，它会直说，
并打印出合适的数字，但**它自己从不写入任何东西**，而且建议有护栏：
绝不上调终止阈值，恢复阈值绝不落在空闲温度带里，数据太少就不给建议。

**6. 能给繁重任务排队（可选）。** 打开 `admission_control` 后，经 `safe-run`
启动的任务要声明占用的核心数（`--cores 6`），guard 按当前热余量放行或排队：
芯片凉快时给全部性能核，温热时给一半，发烫时不放新任务进来。队列在守护进程
重启后仍然保留，`--after 任务名` 可以串起任务链，不用再手写 `pgrep` 循环。
仲裁器只推迟启动：它从不暂停、从不杀进程，内部一旦出错就放行所有人。
默认关闭。

**7. 留下证据（黑匣子）。** 守护进程每个周期写一次心跳，正常关机时另写一个标记。
重启后把两者与本次开机时间比对：心跳在开机之前就断了、又没有正常关机标记，
说明机器是毫无预警地断电的。事件会**连同崩溃前最后八次测量**一起记录下来。
`thermal-report` 把这些整理成维修店能接受的一份文件：硬件与序列号、电池健康度、
硬关机及其之前的读数、guard 的全部干预记录和完整的温度历史。

<p align="center">
  <img src="docs/screens/guard_log.webp" alt="日志中真实的散热故障告警" width="620">
</p>

---

## 和 Caffeine / Amphetamine / Stats 有什么不同

| | Caffeine | Amphetamine | Stats / iStat | coffee-paladin |
|---|---|---|---|---|
| 显示温度 | 否 | 否 | **是** | **是** |
| 保持系统唤醒 | 借助屏幕 | 是 | 否 | **是** |
| 允许屏幕休眠并锁屏 | 否 | 视设置而定 | - | **总是** |
| 机器过热时释放唤醒锁 | 否 | 否 | - | **是（热保险丝）** |
| 暂停让 Mac 过热的任务 | 否 | 否 | 否 | **是** |
| 硬关机前记录黑匣子 | 否 | 否 | 否 | **是** |
| 开源 | 否 | 否 | 部分 | **MIT** |

一句话：Stats 和 iStat Menus 是**仪表盘**，它们告诉你机器有多热。
Caffeine 和 Amphetamine 是**开关**，它们让机器别睡。
coffee-paladin 是**保险丝**，它会自己动手。

---

## 机群：所有 Mac 在同一张表里

越来越多公司把本地 AI 跑在 Mac 上：大内存的 Mac mini 或 Mac Studio，本地模型，
数据不出内网。这些机器 24/7 连轴转，渲染农场、后期工作室和 CI 池也一样。
每台机器把快照写进一个共享目录（iCloud、SMB、NFS 都行），菜单里就出现一张表：
谁热、谁在暂停任务、谁不再上报（沉默五分钟就会打上 STALE 标记）。

<p align="center">
  <img src="docs/screens/fleet.webp" alt="Apple 机群：两台 Mac，其中一台失联" width="620">
</p>

---

## 你的 AI 助手也能和它对话

编码助手如今是笔记本上正常的负载来源，而且往往是最糟糕的那个，因为助手听不见风扇，
也感觉不到机器在发烫。所以本项目附带一份**给 AI 助手的 skill**，
`install.sh` 会把它放进 `~/.claude/skills/coffee-paladin/` 供 Claude Code 使用，
也会放进 `~/.agents/skills/`（OpenClaw 以及一切按 AgentSkills 布局读取的工具）
和 `~/.grok/skills/` - 但只放进已经存在的目录树：我们不会为你没装的工具凭空
建配置。各处都是同一份纯 Markdown 文件。

它教助手四件事：动手前先读 `~/.coffee-paladin/status.json`（`level` 字段说了算：
`0` 开工、`1` 别并行、`2` 别开新的、`3` 停下并告诉人类）；繁重任务通过 `safe-run` 启动；
**绝不**对 guard 冻结的进程发 `SIGCONT`；以及首先就别制造热量：后台任务必须有超时和清理，
不要递归搜索 iCloud 同步目录。最后这条来自一次真实事故：一个 `grep`
在 1 小时 42 分钟里只用了 13 秒 CPU，却让一台无风扇 Mac 稳在 90 °C，
因为它一直逼着 `fileproviderd` 和 `cloudd` 从云端拉取文件。

**Claude Code 状态栏。** 安装器可以把热状态直接写进代理会话下方的状态行，
共两行：第一行是机器的实况，第二行是这个 AI 会话。

```
🛡  🌡 55°  🌀 2.4k  🧠 50%  💾 94%  ☕
🤖 Fable 5  5h 86% ↺14:30  7d 41% ↺Thu  ctx 62%  my-project
```

第二行给出模型、**你账号的用量上限** - 与 `/usage` 界面相同的 5 小时和 7 天
百分比，直接来自 Claude Code 交给状态行的 session JSON（订阅账号；字段在会话
first response 之后出现）- 再加上上下文占用和当前目录。百分比在 75 变黄、
在 90 变红。JSON 里没有上限，行里就不显示：它绝不编造数字。同一份经过白名单
过滤的快照会写入 `~/.coffee-paladin/claude_usage_cache.json`，供菜单栏读取，
于是"我还剩多少 Claude 额度"的答案就在菜单栏上，而不必去敲斜杠命令。终端变窄
时先让位的正是这条 AI 行，从右侧逐个元素退让，并且在丢掉任何一个热学事实之前
就整行消失。

观察模式下盾牌变成眼睛；守护进程的快照过期时变成醒目的红色 `OFF` - 正是
"守护进程停了、心跳丢了而无人察觉"的那种故障。你已有的状态行安装器绝不触碰
（`--replace` 是人的自觉选择），卸载器只删除自己的条目。

**今天用掉了多少。** 如果系统里装了外部的 `ccusage`，"代理活动"子菜单里会多出
一行今日用量，涵盖它认识的所有代理 CLI：`322M 个 token · ~$312`。token 排在前面
是有意的：订阅制下那个美元数字并不是谁真的花掉的钱，而是同样的工作按 API 价格
折算的等价值，所以前面加了 `~`，用 `"ccusage_cost": false` 可以完全去掉。订阅制
真正的预算是 5 小时和 7 天的百分比，就在上面那一行。我们调用别人的可执行文件并把
结果缓存 10 分钟，而不是把别人的代码搬进仓库；没有 `ccusage` 就没有这一行，
其余一切照常。
展开这一行，当天会按**代理**和**模型**拆开，看得出到底是哪个 CLI、哪个模型
吃掉了 token；下面还有**当前的五小时区块**及其速度：`47M 个 token ·
283k/分钟 · 还剩 94 分钟`。这个区块由 ccusage 依据本地文件统计，标注是刻意的：
它不是你账号官方的 5 小时额度，后者有自己的一行，直接来自 Claude Code。
还有一行是任何用量面板都给不出的，因为它同时需要两边的信息：当守卫自己的
预测说芯片会在区块结束前迫使暂停时，它会直说。

**代理活动。** 守护进程写入 `agent_activity.json`：这台 Mac 上有哪些 AI
会话在运行、每个会话启动了怎样的进程树，并附带热上下文。菜单里有按进程
类型配图标的子菜单，菜单栏上的 ✨ 标记在任一会话存活期间点亮 - 标记的
存在本身就回答了"AI 现在在干活吗"。菜单栏同时变得更安静：常驻的只有芯片
和 RAM，其余（风扇、40 °C 起的电池、AI 标记、暂停）只在有消息时出现，
并带 60 秒滞回。

**给所有代理宿主的同一道闸门。** `coffee-paladin hook-gate` 实现了
Claude Code、Codex CLI、Gemini CLI、Grok Build 和 Antigravity 共享的
pre-exec 钩子契约 - 尽管各家方言不同。闸门按宿主说话的拼法读取工具调用
JSON（snake_case 的 `tool_input`、Grok 的 camelCase `toolInput`、
Antigravity 的 `toolCall.args.CommandLine`），再按该宿主听得懂的方式回答：
退出码 2 并把理由写到 stderr，另外为只认这一种答复的两个宿主在 stdout 明确
输出 `{"decision": "deny"}`（Grok 对其他任何回答都放行，Antigravity 根本
没有退出码契约）。裸启动的重型工具 - `ffmpeg`、求解器、`ollama run` - 会被
拒绝，并附上应改用的 `safe-run` 命令行。闸门检查的是进程纪律而非温度，
毫秒级响应，任何意外一律放行：坏掉的闸门绝不能把编码会话扣作人质。
`PALADIN_HOOK=off` 可为一条自觉的命令临时关闭它，config.json 里的
`hook_heavy_patterns` 可替换内置清单。

接线**按宿主自愿启用**，一个宿主一个适配器，每个都守着与 Claude 接线相同的
规矩：自己的条目在文件锁下追加，别人的条目一律不碰，每次写入前留一份带时间戳
的备份，解除时只删掉我们那一条。

```bash
python3 ~/.coffee-paladin/settings_wire.py hook          # Claude Code
python3 ~/.coffee-paladin/codex_hooks_wire.py hook       # Codex CLI（首次运行时确认信任）
python3 ~/.coffee-paladin/gemini_hooks_wire.py hook      # Gemini CLI
python3 ~/.coffee-paladin/grok_hooks_wire.py hook        # Grok Build
python3 ~/.coffee-paladin/antigravity_hooks_wire.py hook # Antigravity
```

（`unhook` 逐个撤销；`uninstall.sh` 会全部跑一遍。）Grok 默认还会扫描
`~/.claude/settings.json` 里的钩子，所以接到 Claude 上的闸门已经把它一并覆盖。
Gemini 的超时字段用的是毫秒，而别家都用秒 - 适配器知道这件事。

**在跑代理集群？你已经被覆盖了。** 那些把 worker 当作普通 CLI 会话拉起来的
编排器（oh-my-claudecode 的 team、claude-squad、workmux、dmux 的窗格）天然
继承这道闸门：每个 worker 都是一个 `claude`、`codex`、`gemini` 或 `grok`
进程，读同一份用户级设置，撞上同一个 PreToolUse。编排器那边什么都不用配。
目前没有任何编排器看得见的，是机器本身：它有多热、还扛得住几个重活。而这
恰恰是守护者守住的那一层：一份任何调度器在扩容前都能读的 `status.json`。

**终端。** 同一条热状态行在代理会话之外也能用：`integrations/terminals/`
提供了 tmux 的 `status-right` 片段、WezTerm 的 `update-status` 处理函数和
iTerm2 的状态栏组件，每个都只有复制粘贴的大小，安装说明就写在文件里。

**进度心跳。** `safe-run` 通过 `$PALADIN_PROGRESS` 递给任务一个文件路径；
任务每完成一个工作单元就触碰它，声明了节奏（`--progress-interval 300`）
之后，守护者会在任务沉默超过三倍声明间隔时诚实地说"可能停滞了" -
永远只是说，绝不发信号。

---

## 安装

**通过 Homebrew（最简单）：**

```bash
brew install pawelkwaczynski/tap/coffee-paladin
bash "$(brew --prefix)/share/coffee-paladin/install.sh"
```

两行都需要：`brew install` 只放置文件，第二行才编译菜单栏应用并启动守护进程。

如果这台 Mac 是用迁移助理从 Intel 机器搬过来的，`/usr/local` 里可能还住着
Intel 版的 Homebrew，光写 `brew` 有可能指向它，而它不认识这个 tap。
这种情况请用完整路径：`/opt/homebrew/bin/brew install ...`。详见 [FAQ](FAQ.md)。

**从源码：**

```bash
git clone https://github.com/pawelkwaczynski/coffee-paladin.git
cd coffee-paladin
bash install.sh
```

两条路径得到的版本完全相同。

安装脚本会在本机编译 Swift 部分，并注册**两个** LaunchAgent：守护进程和菜单栏应用
各一个，后者可以单独关掉而不影响保护。**默认以「仅观察」模式启动**：只测量和告警，
不碰任何进程。确认它看到的东西合理之后，在菜单里点一下「启用保护」，
或在*设置 → 仅观察（dry run）*里取消勾选即可，随时可以再改回来，无需重启。

卸载：菜单里就有**「卸载」**一项（附「连数据一起删除」的勾选框和第二次确认窗口），
或者运行 `bash uninstall.sh`。测量历史和黑匣子默认保留，保修时可能还用得上；
`--purge` 会连它们一起删掉。

## 使用

```bash
heat                            # 一条命令看清现在有多热、什么在发热
heat --profile                  # 从这台机器自己的历史里读出它的热特性
safe-run --hours 8 -- ffmpeg …  # 在监管下启动繁重任务（推荐方式）
thermal-report --days 14        # 生成给维修店的报告（--pdf 输出 PDF）
fleet --setup                   # 配置机群共享目录
heat --paladin                  # 彩蛋 ☕︎
```

`safe-run` 还有为通宵队列准备的开关：`--wait-cool`（机器太热时等它降温再启动，
而不是直接拒绝退出）、`--grace N`（`SIGTERM` 与 `SIGKILL` 之间留几秒，
让求解器或编码器来得及写状态），并且退出时会清理整个进程组，
孤儿子进程再也不能活过自己的监管者、不受时限地烧机器几个小时。

**菜单栏与「刘海」。** 完整的一排读数在 MacBook Pro 的刘海旁边放不下，
这时 macOS 会干脆一个像素都不画，也不给任何提示。所以全新安装常驻的只有
芯片和 RAM（其余为条件显示，有消息才出现）；菜单里有三个预设（「仅图标」「图标与芯片温度」「全部显示」），
同样的预设也能在终端里切换，专门留给看不见图标、打不开菜单的时刻：

```bash
coffee-paladin bar icon-only   # 只剩温度计图标，哪里都放得下
coffee-paladin bar chip        # 图标加一个数字
coffee-paladin bar full        # 全部
coffee-paladin panel           # 绕过菜单栏直接打开窗口
```

升级不会改动你已经选好的布局。

菜单栏、通知和所有命令行工具支持**五种语言**：英语（默认）、波兰语、俄语、中文、西班牙语。
切换按钮就在主菜单上。

## 已知限制

- 暂停对**时间敏感的 I/O** 是可见的：网络对端、看门狗和许可证服务器可能会注意到。
  但不管温度的代价更大：macOS 会全面降频，极端情况下机器硬关机。
- 芯片温度依赖 `macmon`（通过 IOReport 读取，无需 sudo）。没有它，guard 仍然工作，
  但只能依据电池温度和系统热压力，反应会慢几分钟。
- 只支持 **Apple Silicon** 和 **macOS 14 或更新**。Intel Mac 的传感器路径完全不同
  （SMC 而非 IOReport），尚未实现。
- 它不是替代散热维修的东西。如果风扇坏了，它只会更频繁地暂停你的任务，并把这件事记下来。

---

## 许可与署名

MIT。随便用。如果它救了你的机器，那就够了。

作者：Paweł Kwaczyński / FOCUS FRAME，2026。本项目由罗兹 AHE 计算机科学学生科研社团
**AIrON** 的创始人开发。
Swift 部分由 **Claude（Anthropic）** 在 Claude Code 中编写，
**Codex（OpenAI，GPT-5.5）** 担任对抗性评审，另有两个本地模型
（MLX 上的 Devstral 24B 与 Ollama 上的 qwen3:4b）参与复核。

**美术。** 圣骑士吉祥物为**作者的原创设计**，作为本项目的官方形象使用；
细节见 [`branding/CREDITS.md`](branding/CREDITS.md)。
