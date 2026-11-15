# 插件维护约定

## 收到仓库链接后的安装与配置任务

当用户以安装/使用本插件为目的提供仓库链接时，先读 README 的“给 DeepSeek / AI 助手的自动安装入口”，有本地工具能力就实际执行，不要仅转述教程。源码审查或其他请求仍按用户当次目的处理。常规路径发现、独立环境安装和已授权的连接配置不必反复询问；遵循客户端权限规则，缺少关键条件时报告具体缺项，不假装已完成。

执行顺序：

1. 在用户指定目录或可写工作区获取源码；已有副本先检查来源/版本/本地修改，不覆盖未保存工作。记录最终源码绝对路径。
2. 确认 Windows 可交互会话。调用 `load_workspace_dependencies` 获取并验证真实 Python（3.11+、可导入 openpyxl）；不复制开发者路径或 venv，不依赖 Codex，不修改 Harness 基础库。
3. 从运行进程、已安装应用记录、快捷方式和常见目录发现 GetData Graph Digitizer 可执行文件，核对版本；优先已验证的 2.20 Unicode 版本。找不到或多个候选无法确定时，仅询问缺失路径/版本。不要安装或修改 GetData 软件。
4. 用发现的 Python 运行本仓库 `backend/setup.py --getdata-exe <本机真实exe路径>`。首次安装不使用 `--skip-deps`。要求退出码 0、成功消息，以及 selftest_report.json 的 `ok=true, desktop_export_tested=true, tools=9`。无 --getdata-exe 的便携测试不代表软件实际导出通过。失败则检查原始报错和证据，不跳过检查、不伪造 runtime、不用计算后备。
5. 从安装器生成的文件配置连接：有 mcpManager.register 时采用 GitHub 插件及 harness-plugin.patch.yml；否则采用 harness-client.entry.json 的官方 Harness MCP 条目。保留其他配置，必要时备份，只启用一个同名 redframe_digitizer；已有条目只更新本插件部分。installDir 必须指向实际已装好的 backend，不能误用另一个未安装的 GitHub 下载副本。保留 300000 ms 超时。
6. 重新加载后核对 9 工具，再通过合成任务的 view_job_image 验证图片确实进入模型上下文。只有看见工具、仅默认自检通过、或返回了 image 类型，都不能冒充真实模型看图验收。需要用户重启或更换支持图片的模型时，明确报告当前完成范围及剩余步骤。
7. 最终简报源码/解释器/GetData 路径、连接方式和三项验收：实际软件自检、9 工具、模型图片接收。安装成功后说明用户可直接发 PDF 与 Excel 模板。不得将本机配置、密钥、任务或真实文献上传 GitHub。

README 与安装器生成的文件是具体参数依据。安装器不会自动编辑所有 Harness profile；GitHub 插件安装也不会自动完成 Python 后端安装，必须完成上述两个环节。只收到链接而缺少本地执行或配置工具时，应指出能力限制及下一条具体命令，不编造安装结果。

## 后端与维护约定

本插件用 DeepSeek Harness 的 mcpManager 注册一个现有本地 stdio 后端。不要声称模型已识图，除非工具返回图片实际进入模型上下文且完成逐图核对。

0.3.0 使用已安装 GetData 2.20 通过原生 Windows 控件实际导出 TXT，严格比对后才写入 Excel；禁止计算后备导出。需要 Windows 交互会话；仅线性轴导出已验证，对数轴明确阻止。模型负责看图和复核，GetData 负责 GDW 坐标计算及 TXT，程序读取真实 TXT 写表。GDW 量化精度为 1/9 像素，必须保留 TXT 数值及导出证据。

仍使用 Harness load_workspace_dependencies 返回的 Python 和其中的 openpyxl。安装器以 system-site-packages 虚拟环境复用该库，不依赖另一款客户端或其私有表格库，不修改基础运行环境。旧版配置必须重新安装迁移。

后端的完整流程必须放在 MCP server instructions 中；官方 Harness 当前不消费 MCP prompts，不能只依赖 digitize_redframes 提示词。默认只提红框曲线均值点，不含误差棒，不新增观测点；每篇一表，前三词命名，五列为标题／原图指标／X／Y／曲线含义，重复标签、保留数值、零无尾点。

提交 GitHub 只能使用发布白名单。禁止提交 runtime.json、实际用户 PDF/Excel、jobs、venv、账号密钥、Codex 专有运行库、GetData 安装包或破解文件。不要假装 ZIP、GitHub 或 npm 上已经发布了尚未发布的版本。

安装必须指定 --getdata-exe PATH，真正的 GetData → TXT → Excel 自检通过后才更新 schemaVersion=3 的 runtime.json。默认 self_test.py 在 CI 验证缺失 GetData 时拒绝导出；只有 --getdata-exe 模式才证明桌面导出通过。

测试：Node `--test test/plugin.test.mjs` 验证注册契约与失败情况；backend/self_test.py 验证 Python MCP 与 Excel 数值。这些不是在真实 Harness 桌面中做过安装的证明。真实客户端安装仍需验证版本、附件能力、支持图片的模型、工具发现与一次图像任务。

导出后：PNG 是数据摘要，不是实际 Excel 渲染；用 Harness office_render 验收版式。报告 requires_recalculation=true 时先 office_recalculate。后端不算公式。遇到复杂模板对象导致拒绝导出应如实报告，不能绕过保护或保证原生功能完整保留。


0.4.0 新增 refine_panel_points。模型先提交粗点，再按同一裁图像素提供每系列标记形状/半径/线宽。必须查看全部精修叠加图与放大图；每个 needs_review 点在 review_panel 中提供独立 keep_coarse 与原图核验说明。粗点不对则重新 submit 修正；不允许用笼统备注绕过，或将启发式分数当统计置信度。程序不会新增观测点、改轴或改标签，精修/重提撤销旧复核。旧手动任务保留兼容。新服务有 9 工具，配置 schemaVersion 仍为 3。
