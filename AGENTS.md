# 插件维护约定

本插件用 DeepSeek Harness 的 mcpManager 注册一个现有本地 stdio 后端。不要声称模型已识图，除非工具返回图片实际进入模型上下文且完成逐图核对。

后端的完整流程必须放在 MCP server instructions 中；官方 Harness 当前不消费 MCP prompts，不能只依赖 digitize_redframes 提示词。默认只提红框曲线均值点，不含误差棒，不新增观测点；每篇一表，前三词命名，五列为标题／原图指标／X／Y／曲线含义，重复标签、保留数值、零无尾点。

提交 GitHub 只能使用发布白名单。禁止提交 runtime.json、实际用户 PDF/Excel、jobs、venv、账号密钥、Codex 专有运行库、GetData 安装包或破解文件。不要假装 ZIP、GitHub 或 npm 上已经发布了尚未发布的版本。

测试：Node `--test test/plugin.test.mjs` 验证注册契约与失败情况；backend/self_test.py 验证 Python MCP 与 Excel 数值。这些不是在真实 Harness 桌面中做过安装的证明。真实客户端安装仍需验证版本、附件能力、支持图片的模型、工具发现与一次图像任务。
