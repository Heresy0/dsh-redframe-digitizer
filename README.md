# Redframe Digitizer for DeepSeek Harness

面向官方 DeepSeek Harness 桌面/Web 的插件桥接初版。连接本地 PDF 红框取点 MCP，复用 8 个工具：裁图、坐标换算、点位复核、GetData 兼容工程和 Excel 导出。

**状态：0.1.0 源码初版。插件注册契约测试与 Python MCP 测试已通过；尚未在实际 DeepSeek Harness 桌面安装实测，尚未发布到 npm。** 基于官方 0.2.2-rc.3 文档开发，旧版可能没有 mcpManager 注册接口。

源码仓库：https://github.com/Heresy0/dsh-redframe-digitizer 。Harness 的 GitHub 插件来源可填写 `github:Heresy0/dsh-redframe-digitizer`；依赖、后端安装位置和模型图片能力仍需按下文配置，安装插件不等于这些条件已满足。

## 先确认条件

- 官方 Harness 支持 stdio MCP 和旧协议协商；工具图片要求附件功能已启用，当前模型支持图像输入。连接工具成功不等于模型能够看图。
- 官方 MCP prompt templates 当前不受支持；本后端已把完整操作流程放进 server instructions，模型不必读取 MCP prompt 模板。
- 这版仍需要 Windows x64、Python 3.12、已有的 Codex 表格运行库。它不是只装 Harness/GetData 就能独立运行的最终通用版。不会复制或发布 Codex 专有运行库。
- 未来若要彻底去掉 Codex 依赖，需单独实现、验证可分发的 Excel 导出后端；当前未完成该改造。

## 安装顺序

1. 克隆或解压此源码到最终目录，运行 `backend/install.cmd`。GitHub 源码不含 wheelhouse 时会从本机配置的 Python 包索引联网安装依赖；检测不到表格运行库则明确失败。可以将先前分享包的 wheelhouse 放到 backend 下进行离线依赖安装。
2. 安装器自检通过后，backend 内会生成 runtime.json 和客户端连接配置。先在 Harness 的 MCP 设置中按该配置添加 stdio 服务，是最直接的验证方式。超时设为 300000 毫秒。
3. 若希望作为插件加载，使用 Harness 的插件安装页面安装本地这个包，或通过上述 GitHub 安装来源安装。
4. 插件配置 installDir 必须指向第 1 步实际装好、含 runtime.json 的 backend。GitHub 安装插件会创建另一份包，不能假设它自动继承你克隆目录里的虚拟环境。通过 profile patch 设置：

```yaml
- id: redframe-digitizer
  config:
    installDir: 'D:\your-folder\dsh-redframe-plugin\backend'
```

也可让 Harness 启动环境中的 REDFRAME_INSTALL_DIR 指向这个目录。插件只注册服务，不自动执行安装脚本，不改写其他服务器配置。同名 MCP 已在设置中手动添加时，先停用其中一个，避免重名。

5. 查看 `mcp__redframe_digitizer__prepare_job` 等 8 项工具。先调用 view_job_image 确认模型实际能收到图片，再给 PDF 与 Excel 模板。断言已看图之前要有实际图片证据。

## 不装原生插件的备用连接

旧版无 mcpManager 时，可使用其官方 dsh-mcp-client，按 backend/mcp-client.json 中的实际值填入：

```yaml
- id: mcp-redframe
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: redframe_digitizer
    transport: stdio
    command: 'D:\your-folder\backend\.venv\Scripts\python.exe'
    args: ['D:\your-folder\backend\server.py']
    toolCallTimeoutMs: 300000
    startupTimeoutMs: 30000
```

server.py 读取同目录 runtime.json，因此不必在此段抄写三项运行库环境变量。不要覆盖整个已有 MCP servers 映射，以免移除其他服务。

## 输出与限制

助手识别真实坐标刻度和均值标记中心，工具计算与校验。每篇一张表，标题前三词命名；列为文章标题／图片字母（原文 Y 轴指标）／X／Y／线段含义，每行标签写全，零和整数无末尾小数点。仅支持这套五列布局，保留模板已有表。

不会把误差棒端点或连线插值当作观测点；支持线性/log10 二维曲线。GDW 是兼容工程，不代表实际调用过 GetData 界面。不附带 GetData 或破解补丁。不同模型读图精度仍需逐图核对。

## 开发与 GitHub 发布

`node --test test/plugin.test.mjs` 检查插件注册契约；`backend/self_test.py` 检查程序生成的已知点经 MCP 到 Excel。真实桌面、真实 API 和视觉取点尚需在接收者环境验收。

仓库根目录具有 package.json、dsh.bundle 声明和 cordis.patch.yml。发布后可在 GitHub 仓库添加 dsh-plugin topic，供 Harness 插件发现。请使用干净源码白名单，排除 .gitignore 中所有个人状态和运行库。

依据：[官方 MCP 客户端](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md)、[官方插件注册 MCP 接口](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-manager/README.md)、[官方插件管理器](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/boot/plugin-manager/README.md)。
