# Redframe Digitizer for DeepSeek Harness

PDF 红框曲线均值点 → GetData 实际导出 → Excel 模板。插件提供 11 个本地 MCP 工具。

**0.5.0：GetData 2.20 实际负责坐标计算与 TXT 导出；Excel 只读取已核验的真实 TXT。导出失败立即停止，没有计算后备。** 使用 Harness Python 的 openpyxl 写表，不依赖 Codex 或其专有运行库。

仓库：[Heresy0/dsh-redframe-digitizer](https://github.com/Heresy0/dsh-redframe-digitizer)。Harness 插件来源：`github:Heresy0/dsh-redframe-digitizer`。源码 MIT，不分发 GetData 安装包、许可证或破解文件。

## 0.5.0：日常 skill 与 MCP 批处理

固定程序阶段通过两个新增 MCP 工具执行；skill 负责指导模型何时调用、何时停下来识图/复核，本身不是自动执行引擎。

```text
prepare_job（程序准备）
→ 模型确认红框、裁图、识别标定/图例/粗点
→ submit_and_refine（提交、校验、预览、精修、生成复核图）
→ 模型查看叠加图与全部放大图，形成逐点复核意见
→ review_and_export（整批复核预检、实际 GetData、TXT 校验、Excel）
→ 模型按需验收版式并交付
```

原有 9 个单步工具继续保留，现在共 11 个工具。正常任务优先用批处理；局部纠错、长任务复核检查点及导出失败重试仍可使用单步工具。批处理不跳过模型视觉判断，不自动批准候选点。

### Skill 在 Harness 中如何加载

标准 skill 位于 [skills/redframe-digitize/SKILL.md](skills/redframe-digitize/SKILL.md)，参数细节按需读其 references。原生插件通过官方 `ctx.inject(['skills'], ...)` 可选注入和 `ctx.skills.register(...)` 注册 `redframe-digitize`，随插件生命周期管理。已有 skill registry 和模型侧 loader 时，模型可以发现并加载；用户也可使用 `/redframe-digitize`。未挂载 skills 服务或 loader 时，不阻塞 MCP，但不能声称 skill 已加载。

直接连接 MCP 的用户可以在 Harness 已有 skill-filesystem 的 `customSkillDirs` 中增补本仓库 `skills` 的实际绝对路径，保留已有目录。不要把普通 `skills/` 误认为所有客户端默认扫描路径；也可明确让助手读取 SKILL.md 作为工作指导。其他支持标准 SKILL.md 的客户端可按各自方式发现。完整批处理流程仍保存在 MCP server instructions，因此不依赖 MCP prompts 或 skill 加载成功才可调用工具。

安装后分别验收：①11 个 MCP 工具；②`redframe-digitize` 能发现/加载，且相对 reference 可读；③模型实际接收到 view_job_image 图片。前两项不能代替第三项。项目只做了官方接口契约测试，尚未在真实 Harness 桌面完整重装验收。

官方依据：[skill registry](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/skill/skill/README.md)、[filesystem roots](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/skill/skill-filesystem/README.md)、[model/user skill loader](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/skill/tool-skill/README.md)。

### 批处理的一致性和失败恢复

- `submit_and_refine` 在独立 revision 目录写派生文件，两步都成功后才提交面板。失败保留旧状态和旧复核图；失败 revision 仅是诊断文件。
- 结果返回 `revision`。看完该版本图片后，批量复核提交 `expected_revision`；旧版本或源像素变化会被拒绝。单步 review_panel 也支持可选 expected_revision。
- `review_and_export` 先在副本上验证所有复核意见、待复核点、标题、覆盖和轴类型。任一不符则不提交任何复核。
- 预检通过后保存有效复核，再实际导出。软件导出失败会记录 `job_status.last_batch.phase=export_failed`，旧成功工作簿不会冒充新结果；解决故障后可直接重试 export_workbook，无需重做有效复核。
- 同一个 job 仍需串行写入；这是本地阶段提交，不是数据库事务或跨进程任务锁。

真实 MCP 对照测试：两个合成面板、每条路径 12 点，单步与批处理均实际调用 GetData；独立读取 Excel XML，标签/点数/数值一致。状态变更调用从 7 次变为 3 次，排除两边相同的准备、看图、状态查询；不代表实测模型轮数、总 token 或总耗时减少相同比例。[详细验证](docs/batch-validation.md)

升级到 0.5：更新 GitHub 插件本体和实际 backend 源码（可能位于两个目录），重新运行安装器验收，再重载插件或重启 Harness 并重连 MCP。仅重启 MCP 进程不会更新仍在内存中的旧插件代码/skill 注册。配置 schemaVersion 仍为 3，新增 toolsetVersion=5、toolCount=11；旧 9 工具后端会被新插件明确拒绝，避免 skill 调用不存在的工具。任务数据保留。

## 给 DeepSeek / AI 助手的自动安装入口

当前 MCP 已连接时，默认加载日常 skill 处理数据，不执行安装。用户明确要求安装/升级/重新配置，或首次以安装为目的提供本仓库链接时，请先阅读本 README 和 [AGENTS.md](AGENTS.md)，再依次完成下面的本机安装与验收。不要只回复安装教程；有本地执行与配置能力时，实际完成常规步骤。若只是浏览、审查源码等其他请求，应按用户当次目的处理。

用户只需提供本仓库链接；解释器、GetData 路径和连接文件优先在本机发现或生成。缺少必要工具、存在无法判断的多个安装版本、找不到软件或受到权限限制时，应明确报告具体缺项，必要时只询问该缺项。本文不保证所有 Harness 版本或模型都具备安装、配置及看图能力；遵循所在客户端的权限规则。

### 1. 准备源码和本机环境

- 使用用户指定的目录；没有指定时，在可写工作区新建独立目录，取得本仓库源码并记录绝对路径。可使用 git clone，或在没有 Git 时下载 GitHub 源码归档。不要覆盖已有文件；已有副本先检查来源、版本和未提交修改，再决定更新方式。
- 确认当前为 Windows 可交互会话，GetData 已安装并可正常使用。本插件不会安装或修改 GetData。
- 调用 Harness 的 `load_workspace_dependencies`，读取其返回的真实 Python 路径，并验证 Python 3.11+ 和 openpyxl 可导入。不要照搬开发者电脑的路径，不要求安装 Codex，也不要修改 Harness 基础运行库。
- 查找本机 `GetDataW.exe` / `GetData.exe`：优先检查已运行进程的可执行路径、已安装应用记录及快捷方式，再检查常见安装目录。核对找到的是 GetData Graph Digitizer，优先使用本项目已验证的 2.20 Unicode 程序。找不到或多个版本无法确定时，再向用户询问完整路径。

### 2. 实际运行安装器

将发现的绝对路径作为参数传入安装器。下列变量表示刚刚发现的本机路径，必须先赋值，不可原样当作路径执行：

```powershell
# $harnessPython：load_workspace_dependencies 返回的 python.exe
# $setupScript：本仓库 backend\setup.py 的绝对路径
# $getDataExe：本机实际 GetDataW.exe / GetData.exe 路径
& $harnessPython $setupScript --getdata-exe $getDataExe
```

首次安装不要传 `--skip-deps`。安装器在 backend 的独立虚拟环境中安装依赖，并执行“粗定位 → 中心精修 → 逐点复核 → 实际 GetData → TXT → Excel”合成自检。保持桌面会话可用，允许测试窗口正常运行。

安装器还会执行单步/批处理对照测试。必须确认命令退出码为 0、出现 `INSTALLATION AND SELF-TEST PASSED`，且生成的 `backend/selftest_report.json` 中 `ok=true`、`desktop_export_tested=true`、`tools=11`。默认不带 `--getdata-exe` 的 self_test.py 仅验证无 GetData 时拒绝导出，不能代替实际软件自检。失败时读取报错及本次任务的证据日志后排查；不要跳过检查、伪造配置或改成计算后备导出。

### 3. 连接 Harness，保留已有配置

- 优先使用原生插件：来源为 `github:Heresy0/dsh-redframe-digitizer`，配置使用安装器生成的 `backend/harness-plugin.patch.yml`；其中 `installDir` 必须指向刚刚完成安装、含 runtime.json 的 backend。GitHub 插件下载副本可能是另一个目录，不能假设它自动继承虚拟环境。
- 如果当前 Harness 没有插件所需的 `mcpManager.register`，使用安装器生成的 `backend/harness-client.entry.json`，通过官方 `@deepseek-ai/dsh-mcp-client` 直接连接本地 stdio MCP。通用 `mcp-client.json` 供采用 mcpServers 格式的其他客户端使用，不要把该外层格式直接覆盖到 Harness profile。
- 使用客户端支持的配置方式，将生成的条目合入正确 profile。保留其他 MCP、插件、模型及账号配置；必要时先做本地备份。两种连接方式选择一种，同名 `redframe_digitizer` 条目只能启用一个；已有本插件配置时更新对应条目，勿重复追加。
- 保留生成配置中的真实解释器、server.py 路径及 300000 ms 工具超时。按客户端能力重新加载连接；若必须用户重启才能加载，说明尚待重启，不要声称新连接已生效。

### 4. 在真实 Harness 中验收

1. 确认能发现 11 个 `mcp__redframe_digitizer__...` 工具，至少核对 prepare_job、submit_and_refine、review_and_export；使用原生插件时另检查 redframe-digitize skill 可发现/加载。
2. 使用安装自检创建的合成任务调用 `view_job_image`，确认图片实际进入当前模型上下文，模型能够描述图中内容。工具返回成功或工具列表可见，都不能单独证明模型收到了图片。
3. 确认合成任务的 Excel 已生成且实际 GetData 导出证据验证通过。若 Harness 的 `office_render` 可用，可用该合成工作簿检查版式。
4. 当前模型不能接收图片时，报告“后端/连接已通过，但当前模型图片能力尚未验收”，按客户端支持方式选择具备图片输入能力的模型后继续；不要声称已经可以识图提取论文。

完成后向用户简报：源码目录、Python/GetData 实际路径、使用的连接方式、软件自检/11 工具/模型图片接收各自的验收结果，以及任何尚未完成的步骤。不要输出或上传账号密钥、本机 runtime.json 或用户文献。

安装验收完成后，用户直接发送 PDF 和 Excel 模板即可，例如：

> 用 redframe_digitizer 提取这些 PDF 红框里的均值标记点，完成中心精修、叠加图及逐点复核，由 GetData 实际导出，再填入 Excel。每篇一表，名称用标题前三个单词，保留模板原表与格式。


## 0.4.0：粗定位、中心精修与逐点复核

模型负责红框、图例、刻度、系列归属和粗点。提交后调用新增工具 `refine_panel_points`，逐系列提供 `label/shape/fill/radius/stroke_width/search_radius`；尺寸必须基于工具返回的同一裁图像素，不能用屏幕缩略图尺寸。可选 color 为 `[r,g,b]`。支持圆、方、菱形和上下三角，实心/空心；不清楚或不支持时用 `shape: manual`。

程序在有界局部窗口匹配标记形状，保留 coarse/candidate/selected 与启发式分数。不会识别论文语义、搜索整图添加观测点、修改刻度或调整物种/处理标签。形状弱、候选接近、相邻系列干扰、重复/顺序冲突、图边缘、零边界变化时保留原粗点并标记待复核。分数不是统计概率；高分仍必须检查。

用 `view_job_image` 看叠加图和每张放大图：青色为粗点、洋红为选用点、橙色为候选。调用 `review_panel` 时，每个待复核点必须有 `point_reviews:[{label,point_index:1-based,decision:keep_coarse,notes:原图核验依据}]`。如果粗点也错了，重新 `submit_digitization` 提交修正后的坐标，再检查并复核；不能用一个笼统的“已检查”绕过逐点记录。重提或再次精修撤销原接受状态。

已复核的选用点仍由 GetData 实际换算并导出 TXT，程序核对后填 Excel，不改变原有五列格式。`job_status` 返回待解决数量，GetData 证据记录精修/人工确认数量。旧任务未启用精修时保留原手动取点兼容流程；不会偷偷修改旧结果。

测试范围与结果见 [精修对比报告](docs/refinement-validation.md)。默认采用非常保守的门槛，自动覆盖率有限，剩余点需要人工/模型逐点复核；不能据此声称任意曲线都能自动精确提取。

0.3 → 0.4 的配置 schemaVersion 仍为 3；更新源码并重连 MCP，可重新运行安装器验收。旧 0.1/0.2 仍需按下文迁移。工具数量从 8 增加至 9。Harness 桌面中的实际安装与图片传递仍需接收者环境验收。

## 程序与模型分别负责什么

1. MCP 复制 PDF/模板到独立任务目录，渲染页面并检测红框候选。
2. 模型查看原图、正文、图注和图例，确认指标、曲线、坐标刻度及均值标记中心。模型仍负责识图与逐图复核；GetData 不会自动理解论文语义。
3. 程序生成点位叠加图和 GetData GDW。此时的坐标只是计算预览；生成 GDW 本身不代表 GetData 已运行。
4. 复核通过后，`export_workbook` 自动启动独立 GetData，使用 Windows 菜单命令与原生文件控件加载 GDW、选择 TXT、导出并关闭。无需模型点鼠标，也没有键盘模拟或截图定位。
5. 程序读取真实 TXT，检查曲线、点数、有限数值及标定结果；通过后用这些 TXT 数值写入模板副本。
6. 保存 TXT、JPEG、GDW、SHA256、曲线映射和操作日志。Excel 备注记录 TXT 出处；返回 `validation.digitizer=getdata`、`getdata_executed=true` 和逐面板证据。用 Harness Office 工具检查最终版式。

## 环境要求与边界

- Windows 可交互桌面；本机实测为 GetData 2.20 中文界面。GetData 仍是 GUI 软件，不是官方 API 或无桌面命令行。其他版本/语言需要兼容性验收；适配器遇到不认识的菜单或对话框会停止。
- 本机已有可正常运行的 GetData；安装时显式提供 exe 路径，不猜测朋友电脑的安装目录。
- Python 3.11+，优先使用 Harness `load_workspace_dependencies` 返回的 Python，已有 openpyxl；安装器在独立 venv 中补充 MCP/PDF 库，不修改基础运行库。
- 当前实际 GetData 导出仅验证了线性 X/Y 轴；对数轴导出明确拒绝。内部预览换算仍能接受 log10，但不表示该任务可导出。不支持断轴、混用双 Y 轴、倾斜图自动校正等。
- GDW 使用 MF=9，像素点和锚点量化到 1/9 像素。最终数值来自 GetData TXT，可能略异于提交时的全精度计算预览；证据记录 `max_preview_delta`。不把近零值强改成零。
- 只提均值标记中心，不取误差棒端点，不在线段插值生成观测点，不自行添加零时刻。原始识图错误仍需模型纠正。
- 支持约定的普通五列 xlsx 模板。绘图、透视表、切片器、宏等复杂对象会明确拒绝，避免静默丢失。

## 安装与从 0.1/0.2 升级

更新/克隆源码到最终目录。在 Harness 调用 `load_workspace_dependencies` 获取 Python 路径，再执行：

```powershell
& '实际Harness的Python路径\python.exe' '项目目录\backend\setup.py' --getdata-exe '实际GetData路径\GetDataW.exe'
```

也可运行：

```text
backend\install.cmd "Harness的Python完整路径" "GetData完整exe路径"
```

若用另一个 Python 启动安装器，可再加 `--harness-python PATH`。默认从本机配置的包索引安装额外依赖；离线完整 wheelhouse 使用 `--wheelhouse DIR`。移动项目或升级基础运行库后需重新安装。

**安装器必须通过真实 MCP → GetData → TXT → Excel 自检，才写入 schemaVersion=3、digitizer=getdata 的 runtime.json 及客户端配置。** 旧配置会要求迁移，jobs 不删除；旧 runtime 仅备份在本地。安装过程会短暂打开 GetData 测试窗口，请保持 Windows 会话可用。

## 连接

直接 MCP：将生成的 `backend/mcp-client.json` 合入客户端，或使用 `backend/harness-client.entry.json` 的 config。服务名 `redframe_digitizer`，超时 300000 ms；不要覆盖其他服务器配置。

Harness 插件：从 `github:Heresy0/dsh-redframe-digitizer` 安装插件，再把生成的 `backend/harness-plugin.patch.yml` 配置合入 profile：

```yaml
- id: redframe-digitizer
  config:
    installDir: 'D:\your-folder\dsh-redframe-plugin\backend'
```

installDir 必须指向已运行安装器的 backend；GitHub 插件的下载副本不会继承另一个目录的 venv。也可用 `REDFRAME_INSTALL_DIR`。不要与同名直接 MCP 配置同时启用。插件通过 mcpManager 注册 stdio 服务，不自动执行安装器。

基于此前验证的 Harness 0.2.2-rc.3 注册接口；本次验证覆盖本机 MCP 和 GetData，未在真实 Harness 桌面中重新安装验收。模型需支持图片，附件功能需可用。连接成功后确认 11 工具可见，并用 `view_job_image` 验证模型确实收到图像。完整流程已放在 server instructions，不依赖 MCP prompts 支持。

## 调用与输出

给助手 PDF 和 Excel 模板：

> 用 redframe_digitizer 提取这些 PDF 红框里的均值点，按模板填表。每篇一表，前三个单词命名。必须由 GetData 实际导出，核对 TXT 证据后给我最终 Excel。

日常优先使用 `prepare_job`、`read_paper`/`view_job_image`、`crop_panel`、`submit_and_refine`，看完图后 `review_and_export`；`job_status` 用于续做与异常定位，原单步工具用于局部修正或导出重试。页面裁框使用 PDF 点、左上角原点；取点使用工具返回裁图的同一 4 倍像素坐标。

每篇文献新建一表，名称采用标题前三词，重名追加序号。五列：文章标题／图片字母（原图 Y 轴指标）／X／Y／线段表示含义；逐行写全标签。保留模板原表；零显示 0，整数无尾点，不更改底层数值。

`jobs/<job_id>/getdata_exports/<run_id>/` 保存每次真实导出证据，重复导出不会覆盖旧 TXT。`job.json` 保存任务、复核与导出记录；`result.xlsx` 为最新成功结果。缺失软件、未复核、未覆盖文献、对数轴、曲线/点数/坐标不符时拒绝生成新结果。失败后仍存在的旧结果属于上次成功导出，不能冒充本轮结果。

数据预览 PNG 只是摘要，不是 Excel 原生渲染。用 Harness `office_render` 验收工作簿；`requires_recalculation=true` 时先 `office_recalculate`。后端不计算公式。

## 测试

```text
node --test test/plugin.test.mjs
python backend/test_export.py
python backend/test_getdata.py
python backend/test_refinement.py
python backend/test_batch.py
python backend/self_test.py
python backend/batch_self_test.py
python backend/self_test.py --getdata-exe "本机GetData路径"
```

前三项验证插件契约、模板保留和适配器数据来源/失败拒绝。默认 self_test 在 Windows/Linux CI 检查 11 工具、图像返回、复核流程和缺失 GetData 时的拒绝；不冒充桌面测试。只有显式 `--getdata-exe` 才实际验证 GetData → TXT → Excel 的已知六点与零格式。程序回归不等于模型识图准确率测试。

本机还以旧文献两个子图执行了真实 MCP 回归。不要提交 jobs、真实 PDF/Excel、venv、runtime.json、账号密钥或 GetData 软件。
