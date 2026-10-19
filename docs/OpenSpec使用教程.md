# OpenSpec 使用教程（傻瓜版）

> 目标：让你用 OpenSpec 给「AI 闯关学习小程序」加新功能时，**先和 AI 把方案说清楚、再写代码**，避免 AI 一顿乱改。
>
> 一句话理解 OpenSpec：**它是一个"先写需求方案、后写代码"的流程工具。** 你提一个想法，AI 先生成一份方案（放在文件夹里），你审核通过后 AI 才动手写代码，写完归档。

---

## 0. 为什么要用它？

平时直接让 AI "帮我加个错题本"，AI 可能理解跑偏、改错文件、改一半。
OpenSpec 的做法是：

```
提想法 → AI 写方案(不写代码) → 你看方案、改方案 → 满意后 AI 才写代码 → 完成归档
```

好处：**方案错了改方案（便宜），代码写完才发现错（贵）。**

---

## 1. 准备工作（只做一次）

### 1.1 检查 Node 版本

OpenSpec 要求 **Node.js ≥ 20.19.0**。打开终端（Git Bash）输入：

```bash
node -v
```

如果版本低于 20.19.0，用 nvm 升级：

```bash
nvm install 20.19.0
nvm use 20.19.0
```

### 1.2 全局安装 OpenSpec

```bash
npm install -g @fission-ai/openspec@latest
```

装完验证一下：

```bash
openspec --version
```

能打印出版本号就成功了。

---

## 2. 在项目里初始化（只做一次）

进入项目根目录，运行：

```bash
cd /e/AI-Project/ai-learn
openspec init
```

它会问你 **"你用的是哪个 AI 编程工具？"**（Cursor / Claude / Copilot / Codex 等）。
按你实际用的选即可（选错了后面也能改）。选完后，它会：

1. 在项目里创建一个 `openspec/` 文件夹；
2. 告诉你在这个 AI 工具里应该用哪个"斜杠命令"（比如 `/opsx:propose` 或 `/opsx-propose`）。

> ⚠️ 记住它打印出来的命令写法，不同工具拼写略有差别，后面要用。

初始化后目录长这样：

```
ai-learn/
├── openspec/
│   ├── specs/        # 已经实现的功能规格（归档后自动生成）
│   └── changes/      # 正在做的新功能方案（每个功能一个文件夹）
├── backend/
├── frontend/
└── docs/
```

---

## 3. 核心工作流（记住这 4 步就够了）

假设你现在要给项目加一个 **「错题本」** 功能。

### 第 1 步：提想法，让 AI 写方案

在你的 AI 编程工具（比如 Qoder / Cursor）的对话框里输入：

```
/opsx:propose 给小程序加一个错题本功能：用户答错的题目自动收集，
可以在"我的"页面查看错题列表，支持重新作答和查看讲解。
后端 FastAPI + MySQL，前端 Taro。
```

> 💡 如果想法还很模糊，不知道怎么做，先用 `/opsx:explore` 让 AI 陪你聊、帮你理清思路，聊清楚了再 `/opsx:propose`。

AI 会**只写方案、不写代码**，在 `openspec/changes/` 下生成一个文件夹，例如：

```
openspec/changes/add-mistake-notebook/
├── proposal.md   # 为什么做、要改什么（概览）
├── specs/        # 具体需求 + 场景（用 WHEN/THEN 描述）
├── design.md     # 技术方案（数据库表、接口设计等）
└── tasks.md      # 实现清单（一条条待办）
```

### 第 2 步：审核方案（最重要！）

打开上面这几个 `.md` 文件，**当成产品文档来读**，重点看：

- `proposal.md`：范围对不对？有没有多做/少做？
- `specs/`：需求场景是不是你想要的？
- `design.md`：数据库表、接口设计合不合理？（对照你项目已有的 `sql/` 和后端结构）
- `tasks.md`：任务拆得清不清楚？

**不满意就直接改这些 md 文件**，或者继续对 AI 说：

```
方案里错题列表要支持按关卡筛选，帮我在 specs 和 tasks 里补上。
```

反复改到满意为止。**这一步不改代码，随便折腾都不怕。**

### 第 3 步：让 AI 按方案写代码

方案确认后，输入：

```
/opsx:apply
```

AI 会照着 `tasks.md` 一条条实现，每完成一条会打勾。
你可以边看边验证，中途不满意随时喊停、回去改方案。

### 第 4 步：完成后归档

功能做完、测试通过后，输入：

```
/opsx:archive
```

它会把这个 change 移动到 `openspec/changes/archive/日期-add-mistake-notebook/`，
并把规格合并进 `openspec/specs/`，作为"项目已实现功能"的正式记录。

**然后就可以开始下一个功能了，重复这 4 步。**

---

## 4. 常用命令速查表

在**终端**里运行（不是对话框）：

| 命令 | 作用 |
|------|------|
| `openspec init` | 项目里初始化（只做一次） |
| `openspec list` | 列出当前所有正在做的 change |
| `openspec validate <change名>` | 检查某个 change 的方案格式是否合规 |
| `openspec show <change名>` | 查看某个 change 的详情 |
| `openspec archive <change名>` | 归档已完成的 change（也可用 `/opsx:archive`） |
| `openspec update` | 升级后刷新 AI 指令/斜杠命令 |

在 **AI 对话框**里输入（斜杠命令）：

| 命令 | 作用 |
|------|------|
| `/opsx:explore` | 想法模糊时，让 AI 陪你理清思路（不写方案） |
| `/opsx:propose 描述` | 让 AI 写一份新功能方案（不写代码） |
| `/opsx:apply` | 让 AI 按方案实现代码 |
| `/opsx:archive` | 归档已完成的功能 |

> 不同工具斜杠命令拼写可能不同（`/opsx-propose`、`@opsx-propose` 等），以 `openspec init` 打印出来的为准。

---

## 5. 升级 OpenSpec

```bash
npm install -g @fission-ai/openspec@latest   # 升级 CLI
cd /e/AI-Project/ai-learn && openspec update  # 刷新项目里的 AI 指令
```

---

## 6. 常见问题

**Q：一定要用斜杠命令吗？直接用终端行不行？**
A：核心流程（propose/apply）靠斜杠命令让 AI 干活最方便；终端命令（list/validate/archive）主要用于查看和管理。两者配合用。

**Q：`openspec/` 文件夹要提交到 git 吗？**
A：要。它就是项目的"需求方案库"，团队和 AI 都靠它对齐，属于项目资产。

**Q：方案写到一半想改需求怎么办？**
A：直接改 `changes/xxx/` 里的 md 文件，或让 AI 改。OpenSpec 是"流动式"的，任何时候都能改任何文件，没有强制阶段门槛。

**Q：AI 工具没在 `init` 列表里（比如 Qoder）怎么办？**
A：选一个通用的/Claude 风格的即可，生成的 md 方案文件是通用的；实在不行也可以让 AI "参考 openspec/changes 里的方案" 手动实现，再自己 `openspec archive`。

---

## 7. 一张图记住全流程

```
 你                     AI                      结果
 ─────────────────────────────────────────────────────
 提想法  ──/opsx:propose──▶  写方案(不写码)  ──▶  changes/xxx/*.md
 审核/改方案 ◀──────────────  按你要求调整
 满意了  ──/opsx:apply────▶  照 tasks 写代码 ──▶  backend/ + frontend/ 改动
 做完了  ──/opsx:archive───▶  归档 + 更新规格 ──▶  archive/ + specs/
```

**核心口诀：先方案、后代码；方案随便改，代码不乱来。**
