# Changelog

## 0.2.0

- 用 Harness Python 中的 openpyxl 写表，移除旧专有运行库、Node 导出器及环境变量要求。
- 安装器接收 Harness load_workspace_dependencies 提供的解释器，继承其已有 Office 库，在本地 venv 补充 MCP/PDF 依赖。
- 新配置 engine=openpyxl；旧版本须重新运行安装器，任务数据保留。
- 保存后回读检查模板和数值，拒绝可能丢失复杂对象的模板。
- 数据预览明确标注非原生渲染；公式重算/实际渲染交由 Harness Office 工具。
- 扩充 Excel 回归测试，CI 增加 Windows/Linux 端到端程序测试。

## 0.1.0

- 初版 Harness MCP 插件桥接、GetData 兼容工程和五列表格导出。
