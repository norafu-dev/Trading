# Signal Desk — AI Trading MVP

项目目标是从 Discord 指定 Trader 的消息中采集交易信息，通过 AI 解析成结构化
信号，再按规则生成 Execution，最终通过 CCXT 接入 Bitget 自动交易 / 跟单。
先跑通 MVP，再扩展；目前正在完成采集和样本积累的基础工作。

## 项目文档入口

- **[项目目标、完整技术栈与阶段规划](docs/PROJECT_OVERVIEW.md)**：最初讨论的整体方向和已确认约定。
- **[系统架构](docs/ARCHITECTURE.md)**：目标模块、当前 Docker 架构、数据流与后续接入边界。
- [代码规范](docs/CODE_STANDARDS.md)：shadcn/ui、PC 端范围、中文注释和前后端编码要求。
- [AI 开发流程](docs/AI_WORKFLOW.md)：开工阅读与交付检查要求。

本 README 侧重当前版本的启动、使用和代码导航。Redis / Celery、AI 解析、Execution
和 CCXT / Bitget 仍在总体规划中，尚未接入当前运行链路。

## 当前运行链路

当前阶段是 Discord 消息采集。运行链路：

```text
Next.js 管理面板 → FastAPI → PostgreSQL 来源配置
                                  ↑
Discord → 独立 Collector → 消息快照 / 版本 / 心跳 / 运行事件
```

所有依赖安装、运行、迁移和自动化测试均在 Docker 中进行。源码保存在本项目目录，不需要本机 Python / Node 环境。

## 启动与访问

启动 Docker Desktop，然后在项目根目录执行：

```bash
make setup
make up
```

打开 [http://localhost:3000](http://localhost:3000)。当前面板是本机单用户应用，Web 端口仅绑定 `127.0.0.1`；API 与 PostgreSQL 不对宿主机开放端口。

`postgres`、`api`、`web` 和 `collector` 都使用 `restart: unless-stopped`。Docker
Desktop 登录后启动时，这些原本处于运行状态的容器会自动恢复；执行 `make stop` 会
移除容器，之后仍需再次执行 `make up`。本机 Docker Desktop 已开启登录自启动。

`make setup` 只在 `.env` 不存在时复制示例，不覆盖配置。Makefile 自动适配 `docker compose` 与独立 `docker-compose`。

## 在面板中管理采集来源

点击 **添加来源**，填写：

- 频道名称：消息浏览页左侧显示的频道或 Thread 名称。
- KOL 名字：消息列表中显示的名称，不再用作者 ID 代替。
- 频道 / Thread ID：实际消息所在的 Channel 或 Thread 的数字 ID。
- Trader 作者 ID：可填写多个，每行一个或用逗号分隔。
- 是否启用。

保存、编辑、启用、停用和移除都直接写入 PostgreSQL。Collector 连接成功后通常约 5 秒刷新配置，无需重启。相同位置配置为一个来源，可在其中添加多个作者。父频道不会自动包含子 Thread；Forum 父频道也不能当作文本消息源。

Collector 会验证频道可访问性。无法访问的来源显示错误，暂不采集，并约每 30 秒重试；其他有效来源可以继续运行。只有频道校验成功后才加载作者过滤规则。停用/删除来源不删除任何历史消息。

旧的 `config/sources.toml` **不再被读取，也不会自动导入**。现有配置需通过面板录入。保留示例文件仅用于历史参考。

## 按分组和频道浏览消息

从侧栏打开 **消息浏览**，或访问 [消息页面](http://localhost:3000/messages)。
页面采用 Discord 式 PC 布局：左侧以单行显示频道，支持自定义分组和拖拽排序，
右侧查看该频道内已采集的消息。分组可新增、重命名和删除；删除分组只会把频道移回
“未分组”，不会删除来源或历史消息。

消息按时间从早到晚排列，每 5 秒刷新，可加载更早的已入库消息；向上阅读时不会
强制滚回底部。停用或删除来源后仍可浏览历史记录。这里的翻页只读取数据库，
不会因为用户翻页而向 Discord 请求更多历史。

消息列表优先使用来源配置中的 KOL 名字，不显示头像。附件图片直接显示，普通附件
提供打开链接；Discord Embed 支持描述、字段、页脚、时间、强调色和 Discord 代理
图片。当前按纯文本保留换行，不解析 Discord Markdown 或提及样式。

## Discord Token 与运行状态

采集使用的是 **`discord.py-self==2.1.0`**。它的 Python 导入名为 `discord`，所以代码
中的 `import discord` 和 `discord.Client` 不代表安装了普通的 `discord.py`。
依赖声明见 `backend/pyproject.toml`，锁文件中的规范化包名为 `discord-py-self`。
Collector 继承该库的 `Client`，通过 `client.start(token, reconnect=True)` 登录用户
账号，由 `on_message` 接收 Gateway 新消息，再按来源规则过滤并入库。首次连接和会话
恢复时，会从每个频道最后一条已保存消息之后读取最多 1000 条近期记录；仍按作者过滤，
并复用消息主键和版本指纹去重。超过窗口的更早缺口需要后续持久化游标方案处理。
导入方式可对照 [discord.py-self 官方快速开始](https://discordpy-self.readthedocs.io/en/latest/quickstart.html)。

Token 只在本地 `.env` 中设置：

```dotenv
DISCORD_TOKEN=你的本地Token
```

不要把 Token 发送到聊天或提交到 Git。设置后执行 `make collect` 重建 Collector 容器以加载环境变量。面板与 API 不接收、不返回 Token。

Token 为空时，Collector 容器仍会运行并报告心跳，状态为 **等待配置 Token**；不会连接 Discord。面板区分进程在线与 Discord 已连接，显示最近心跳、启动时间、配置同步时间、加载来源数、最后入库时间、运行事件和最近 20 条原始消息。

状态约每 5 秒刷新；超过 30 秒没有心跳会显示 **心跳已过期**。API 不可达时明确显示数据可能过期，而不是继续声称服务健康。运行事件保存在数据库中，不向浏览器转发包含凭证或消息参数的原始服务日志。

## 常用命令

```bash
make up        # 构建、迁移，启动数据库 / API / 面板 / Collector
make check     # 容器内检查数据库及迁移
make collect   # 更新并重新创建 Collector（例如修改本地 Token 后）
make logs      # 查看 Collector 服务日志
make frontend-check # ESLint、Prettier、TypeScript 与 Next.js 生产构建
make backend-check  # Ruff、迁移一致性检查与隔离数据库测试
make quality        # 顺序执行以上两组检查
make test      # backend-check 的原有入口
make db-shell  # PostgreSQL 交互终端
make stop      # 停止项目，保留数据库命名卷
```

更新源码后执行 `make up` 重新构建；当前使用生产构建，无热重载。只构建前端可执行 `docker compose build web`，构建包含 ESLint、Prettier、TypeScript 检查。

PostgreSQL 使用 `postgres-data` 命名卷。不要对有价值的数据执行 `down -v`。测试使用独立 `test-postgres` 和独立凭证，不读取采集数据库；测试后可执行 `docker compose --profile test stop test-postgres`。

## 代码结构

```text
compose.yaml                     全部服务、持久卷与测试环境
frontend/
  app/page.tsx                   Server Component 页面组合入口
  features/collector/
    dashboard.tsx                面板组合与来源操作
    api.ts / types.ts            HTTP 请求与 API 类型契约
    use-dashboard.ts             轮询、请求互斥与卸载取消
    source-editor.tsx            来源表单和输入反馈
    source-delete-dialog.tsx      来源移除确认与错误反馈
    sources-panel.tsx            来源搜索、状态及操作列表
    runtime-panel.tsx            进程心跳与 Discord 会话
    overview.tsx                 采集概览指标
    events-panel.tsx             服务与配置事件
    messages-panel.tsx           原始消息列表
    presentation.ts / sidebar.tsx 状态文案、时间格式和静态导航
  app/globals.css                Tailwind 入口与统一主题 token
  components/ui/                shadcn 基础组件及中文说明
  components.json               shadcn CLI 配置与路径别名
  lib/utils.ts                  Tailwind 条件类名合并
  next.config.ts                 同源 API 代理
  Dockerfile                     容器内规范检查和生产构建
backend/
  pyproject.toml / uv.lock        Python 依赖声明与锁定
  migrations/                    0001 消息；0002 来源和运行状态
  src/trading/
    api.py                       生命周期、中间件与异常映射
    http/routes.py               HTTP 路由和数据库依赖
    schemas.py                   请求、响应和来源记录契约
    services/sources.py          来源配置与审计事件事务
    services/dashboard.py        概览组合与心跳状态判断
    cli.py                       check / collect 入口
    config.py                    环境变量与消息源契约
    collector/client.py          Discord 回调、消息写入重试与心跳
    collector/subscriptions.py   来源校验、订阅、具名缓存及重试
    collector/runtime.py         进程启动、等待配置与信号退出
    collector/messages.py        原始消息标准化
    db/models.py                 数据模型
    db/repository.py             消息快照事务与幂等写入
    db/control.py                来源加载、状态和事件写入
    db/sources.py                来源 SQL 与同事务事件写入
    db/dashboard.py              概览数据查询
  tests/                         单元测试与真实 PostgreSQL 集成测试
```

`messages.message_id` 是主键；`message_versions` 通过 `(message_id, fingerprint)` 防止重复快照。当前内容与历史版本在同一事务提交，旧版本不覆盖新内容。Discord ID 保存为字符串，避免浏览器整数精度丢失；时间包含时区。

## 当前边界

- 已实现新消息监听、来源过滤、幂等入库、快照版本存储，以及管理面板与运行状态。
- 当前只保留所选作者的消息。被引用但未采集的消息仅保留引用 ID，不声称已获取正文。
- 已实现启动和会话恢复后的有界近期补采；编辑和删除事件、持久化频道游标及超过
  1000 条窗口的完整历史补采仍待实现。
- 附件与 Embed 保存在快照中并通过 Discord URL 展示；文件未下载到本地，原始 URL
  可能过期，附件归档和样本导出仍待实现。
- 不包含 AI 解析或 Bitget 下单。先积累真实样本，再分析 Trader 风格。
- 单 Collector 实例；当前未提供多副本调度。前端只能启停来源，不通过 Docker Socket 控制容器。

验证包括来源 CRUD、重复配置与非法输入、心跳过期、配置热更新与失败来源隔离、删除来源保留消息，以及消息并发去重。真实 Discord 登录、来源权限与采集验收仍需实际 Token 和频道配置。

接口参考：[discord.py-self](https://discordpy-self.readthedocs.io/en/latest/)、[FastAPI 异步测试](https://fastapi.tiangolo.com/advanced/async-tests/)、[Next.js 自托管](https://nextjs.org/docs/app/guides/self-hosting)。

## 开发规范

先阅读 [代码规范](docs/CODE_STANDARDS.md) 和 [AI 开发流程](docs/AI_WORKFLOW.md)。
根目录 `AGENTS.md` 保留 Thinking Coach 工作偏好并指向这些规范。按业务职责拆分，
不设置机械行数限制，不给简单操作增加没有价值的层次。来源配置修改与审计事件
由 Service 明确控制同一事务；Collector 与 API 共用来源记录契约。

前端新增 ESLint 与固定版本 Prettier，继续使用 npm 锁文件；后端沿用 Ruff 和 uv。
ESLint 暂锁定 9.x，因为当前 Next 配套的 `eslint-plugin-react` peer dependency
尚不接受 10.x；npm 会显示 ESLint 9 的生命周期提示。后续随官方插件兼容性一起升级，
不使用 `--force` 或 `--legacy-peer-deps` 绕过依赖约束。

本次规范重构验证：20 项后端测试通过，包含配置与审计写入失败时整体回滚、
配置更新后重新校验，以及不存在的来源不写入审计事件。前端规范检查、类型检查、
生产构建通过；浏览器验证添加、编辑、非法输入、搜索空态和心跳显示。
本机服务已重新构建运行。真实 Discord 登录与消息接收仍待实际配置后验收。

## UI 与注释约定

现有面板已经迁移到 **shadcn/ui + Tailwind CSS**。按钮、卡片、输入框、Dialog、表格、
Switch、Checkbox、Badge、Alert 和分隔线统一放在 `frontend/components/ui/`。
采集业务组合留在 `features/collector/`，主题变量集中在 `app/globals.css`；不再维护
独立的按钮、表格、开关和弹窗 CSS。移除确认也使用统一 Dialog。

当前只验收 **PC 桌面端**，业务布局不含手机/平板断点，功能完善后再安排适配。
shadcn 官方组件内部的默认响应式类可以保留。技术接入依据
[shadcn 现有 Next.js 项目安装说明](https://ui.shadcn.com/docs/installation/next)。

每个手写源码文件和每个函数都有中文说明，Python 用 docstring，TypeScript 用 JSDoc。
基础 UI 源码也遵守此约定；JSON、生成文件与锁文件不添加非法或易被覆盖的注释。
用户本地 `.env` 和旧来源配置不因注释任务被修改。详细规则见
[CODE_STANDARDS.md](docs/CODE_STANDARDS.md)，入口和交付检查分别在
`AGENTS.md`、`docs/AI_WORKFLOW.md`。

### 不支持注释或由工具生成的文件

| 文件 | 用途与维护方式 |
| --- | --- |
| `frontend/package.json` | npm 脚本与依赖声明；依赖通过 Docker 中的 npm 安装更新 |
| `frontend/package-lock.json` | npm 自动生成的精确依赖锁，不手写注释 |
| `frontend/tsconfig.json` | 严格 TypeScript 检查及 `@/*` 路径别名 |
| `frontend/components.json` | shadcn 风格、主题入口和组件输出路径 |
| `frontend/.prettierrc.json` | Prettier 格式规则 |
| `frontend/next-env.d.ts` | Next.js 自动生成的环境类型声明 |
| `backend/uv.lock` | uv 自动生成的 Python 依赖锁 |
| `.next/`、`node_modules/`、`*.tsbuildinfo` | 构建、依赖和类型缓存，不作为手写源码维护 |

新增 shadcn 组件在 Docker 中使用已锁定的 CLI；加入后核对路径别名、补充中文注释、
运行 `make frontend-check`。当前组件使用 `@/lib/utils` 的 `cn`；官方 CLI 输出如果
使用裸 `cn` 导入，应统一回项目工具函数，避免维护两套类名合并实现。

本次 shadcn 迁移验收已完成 `make quality`：前端 lint/format/类型/生产构建通过，
后端 20 项测试通过。检查了 30 个 Python 文件、83 个函数和 31 个前端源码文件、
67 个具名函数/方法的说明，未发现遗漏；迁移操作 AST 对比保持不变。
浏览器完成添加、编辑、启停、输入校验、移除确认/取消测试；1280px 与 1440px
PC 布局正常，无控制台错误。临时测试来源已清理，审计事件保留。
