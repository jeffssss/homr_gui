<img width="172" height="203" alt="Snipaste_2026-05-12_20-01-11" src="https://github.com/user-attachments/assets/cc08dc83-b856-46c4-8b37-aabc2e652519" />

# HOMR GUI (Music Score to MusicXML)

本项目是基于 [liebharc/homr](https://github.com/liebharc/homr) 的 GUI 封装与增强版本。

### 主要改进：
* **可视化界面**：增加了基于 PyQt6 的交互界面，告别命令行。
* **MusicXML 导出**：支持从剪贴板截图识别乐谱，并保存为 MusicXML 文件。
* **模式切换**：默认入口自动检测 GPU 可用性；CPU 兼容模式脚本仍保留。
* **国内优化**：优化了模型下载逻辑，使用镜像代理提升下载速度。

### 开源协议：
本项目遵循 **GNU AGPLv3** 协议。
