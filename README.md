# Redframe Digitizer for DeepSeek Harness

官方 DeepSeek Harness 桌面/Web 的 PDF 红框曲线取点插件桥接。服务提供 8 个 MCP 工具，助手负责看图与核验，工具负责裁图、坐标换算、保存 GetData 兼容工程和写入 Excel。

**0.2.0：Excel 后端已改为 Harness Python 自带的 openpyxl。无需安装 Codex，无需 artifact-tool、Node 表格导出器或专有表格运行库。** Harness 自身的 Node 插件宿主仍由 Harness 提供，Python 后端不再调用 Node。

仓库：https://github.com/Heresy0/dsh-redframe-digitizer 。插件来源：`github:Heresy0/dsh-redframe-digitizer`。

状态：本地插件契约测试、Python MCP/Excel 自检、模板保留回归测试已通过；真实 Harness 桌面安装及模型图片传递仍需接收者环境验收。基于官方 0.2.2-rc.3 的 mcpManager 接口，旧版可使用下文直接 MCP 连接。

## 安装：使用 Harness 已有的 Python

1. 克隆或解压仓库到最终使用位置。在 Harness 里让助手调用 `load_workspace_dependencies`，获取其 `python` 路径；不要猜测安装目录。
2. 用返回的解释器运行安装器。例如 PowerShell：

```powershell
& '实际的Harness解释器路径\python.exe' '项目目录\backend\setup.py'
```

也可以运行 `backend\install.cmd "实际的Harness解释器路径\python.exe"`。如果启动环境已经提供有效 `DSH_PRIMARY_RUNTIME`，install.cmd 会尝试其 `dependencies/python/python.exe`；否则会显示上述操作说明。

3. 安装器首先检查所选 Python 的 openpyxl，创建继承其已有库的 `.venv`，仅向该虚拟环境补充 MCP/PDF 等依赖，**不会修改 Harness 的运行库**。默认使用本机配置的包索引联网安装；如果有完整且版本匹配的 wheelhouse，可传入 `--wheelhouse "目录"`。Python 要求 3.11+。
4. 完整自检通过后才生成本机 `runtime.json`、通用 `mcp-client.json`、Harness 原生 `harness-client.entry.json` 和插件设置 `harness-plugin.patch.yml`。这些文件包含本机路径，禁止提交到仓库。

也可用另一个 Python 先启动安装器，再显式选择 Harness 解释器：

```text
python backend/setup.py --harness-python "Harness返回的Python路径"
```

安装后的目录或 Harness 运行库若移动/升级，需要重新运行安装器。虚拟环境使用 Harness 基础 Python，不能直接复制到其他电脑。

## 连接方式一：直接连接 MCP

Harness 的 MCP 设置中使用生成的 `backend/harness-client.entry.json` 的 config，或把该 entry 合入正确的 profile。它含真实解释器、server.py 和 300000 毫秒超时。不要直接覆盖整个已有服务器映射。

服务名：`redframe_digitizer`。连接成功后应列出 `mcp__redframe_digitizer__prepare_job` 等 8 个工具。当前模型必须支持图像输入，Harness 附件功能也必须启用；工具列表可见并不能证明模型收到图片。

## 连接方式二：作为 Harness 插件

在插件页面按 GitHub 来源安装 `github:Heresy0/dsh-redframe-digitizer`，将生成的 `backend/harness-plugin.patch.yml` 设置合入 profile。例如：

```yaml
- id: redframe-digitizer
  config:
    installDir: 'D:\your-folder\dsh-redframe-plugin\backend'
```

installDir 必须指向**已运行安装器并生成 runtime.json 的 backend**。通过 GitHub 安装的插件通常是另一份源码，不能假设它继承了克隆目录的虚拟环境。也可在 Harness 启动环境中设置 `REDFRAME_INSTALL_DIR` 指向该目录。

插件用 mcpManager 注册 stdio 服务，生命周期随插件启停；不自动运行安装脚本，不修改其他 MCP 配置。不要同时使用相同 serverName 的直接 MCP 配置和插件连接。

官方 Harness 当前不消费 MCP prompt templates，本后端已经把完整工作流程放在 server instructions 中；不依赖读取 digitize_redframes prompt。

## 升级 0.1.0

更新插件代码后，用 Harness Python 重新运行 setup.py。安装器把 runtime.json 改为 `engine: openpyxl`，连接配置不再传入旧的导出器环境变量。旧 runtime.json 仅在本地备份为 runtime.before-0.2.local.json；不会上传。

新版插件发现旧 runtime 配置会明确要求重新安装，不能直接复用 0.1.0 的安装结果。你的 jobs 文献与任务不被删除。旧版 ZIP 分享包仍是旧实现，请使用本仓库 0.2.0 源码。

## 提取和输出

给助手 PDF 和 Excel 模板即可按 AGENTS.md 流程处理。只提取红框曲线的均值标记点，不取误差棒端点、不用连线插值补点。坐标轴支持线性/log10；仍需模型识别刻度、曲线和图例，不能保证任意图都能无人复核准确读取。

每篇一张新表，标题前三词命名；五列为文章标题／图片字母（原图 Y 轴指标）／X／Y／线段含义。每行标签写全，保留底层数值，零及整数无尾部小数点。模板原表的单元格内容、样式、普通备注、超链接、合并、行高列宽和冻结状态经过保存后回读检查。

当前只支持约定的普通五列模板。含绘图/图片、透视表、切片器、宏、ActiveX 等复杂对象的模板会明确拒绝导出，避免 openpyxl 静默丢失对象。不是完整 Excel 原生功能兼容器。

### 预览与公式

PIL 生成的是前几行的**数据预览**，不冒充 Excel 原生渲染。助手应使用 Harness 的 `office_render` 检查实际工作簿；若导出报告 `requires_recalculation: true`，先用 Harness 的 `office_recalculate`，再渲染。后端本身不计算公式，保存可能使原模板的公式缓存需要重算；公式文本会保留。

GDW 是 GetData 兼容工程，不代表实际调用 GetData 界面。本项目不分发 GetData 安装包或破解文件。

## 测试

```text
node --test test/plugin.test.mjs
<已安装依赖的Python> backend/test_export.py
<已安装依赖的Python> backend/self_test.py
```

- Node：插件注册、缺失环境、旧配置升级提示。
- Excel：模板内容/样式/备注/公式/合并保留、大小写重名、数值精度、零格式、文字以等号开头时不变成公式、复杂模板及非有限坐标拒绝导出。
- MCP：8 工具发现、server instructions、自生成红框 PDF 的已知点到 Excel、独立读取输出 XML。清除旧运行库环境变量后测试。
- GitHub CI 在 Windows/Linux 运行这些程序测试；不代表真实桌面、真实 API 或视觉取点准确率已经验收。

源码采用 MIT。禁止上传 jobs、真实文献、虚拟环境、runtime.json 或密钥。

依据：[Harness 运行库工具](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/tool-catalog.md#deepseek-aidsh-tool-workspace-dependencies)、[Harness Office 工具](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/tool-catalog.md)、[官方 MCP 客户端](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md)、[插件注册接口](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-manager/README.md)。
