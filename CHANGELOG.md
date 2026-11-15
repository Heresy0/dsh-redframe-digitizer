# Changelog

## 0.4.0

- 新增 refine_panel_points：基于明确形状/大小提示的局部中心匹配，保留粗点、候选、选用点及启发式分数。
- 生成叠加与逐点放大图；不可靠结果保留粗点，逐点复核记录缺失时拒绝接受和导出。
- 增加邻近系列、重复/顺序、低对比、图边缘与零边界保护；重提和重精修撤销原接受。
- GetData 继续实际生成 TXT，Excel 使用真实 TXT；完善原生错误对话框和进程退出诊断。
- 增加已知中心/线条/误差棒/歧义/复核门槛测试，完成旧文献受控偏移对比与真实 MCP/GetData 回归；详见 docs/refinement-validation.md。

## 0.3.0

- Windows 原生菜单/控件适配器实际启动 GetData 2.20，加载已复核 GDW 并导出全部曲线 TXT，无鼠标或键盘模拟。
- Excel 从真实 TXT 填表；曲线、点数、坐标校验失败立即停止，无计算后备。
- 保存 TXT、GDW、JPEG、SHA256、执行日志和曲线映射，Excel 备注记录数据出处。
- 旧任务重新生成 JPEG-backed GDW；使用 ASCII 曲线 ID 避免旧 TXT 编码丢失语义。
- 配置 schemaVersion=3、digitizer=getdata，安装时必须指定 GetData 路径并通过桌面端到端测试；旧版本需重新安装迁移。
- 当前只验证线性轴；对数轴导出明确拒绝。
- 增加导出数据来源、缺失/失败不写表、解析异常、量化精度测试；CI 与本机桌面验证分开报告。

## 0.2.0

- 用 Harness Python 中的 openpyxl 写表，移除旧专有运行库、Node 导出器及环境变量要求。
- 安装器接收 Harness load_workspace_dependencies 提供的解释器，继承其已有 Office 库，在本地 venv 补充 MCP/PDF 依赖。
- 新配置 engine=openpyxl；旧版本须重新运行安装器，任务数据保留。
- 保存后回读检查模板和数值，拒绝可能丢失复杂对象的模板。
- 数据预览明确标注非原生渲染；公式重算/实际渲染交由 Harness Office 工具。
- 扩充 Excel 回归测试，CI 增加 Windows/Linux 端到端程序测试。

## 0.1.0

- 初版 Harness MCP 插件桥接、GetData 兼容工程和五列表格导出。
