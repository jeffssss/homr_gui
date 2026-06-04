# HOMR GUI 项目架构

本文档面向准备接手修改这个 fork 的开发者，说明当前工作区里的架构、运行时调用链，以及本项目相对上游 [liebharc/homr](https://github.com/liebharc/homr) 已经做出的 GUI 包装和运行时改造。

## 项目定位

上游 HOMR 是一个 Optical Music Recognition (OMR) 引擎，目标是把乐谱图片转换成 MusicXML。上游 README 描述的核心流水线是：图像分割和结构分析、五线谱检测与合并、基于 Transformer 的语义符号识别、MusicXML 输出。

这个 fork 在上游引擎外面增加了桌面 GUI 工作流，把“命令行传入图片并输出 MusicXML”包装成“截图到剪贴板、后台识别、输出 MIDI、拖入 DAW”的交互方式。

```text
Windows screenshot clipboard
        |
        v
PyQt6 HomrGui
        |
        v
temp_score.png
        |
        v
WorkerThread
        |
        v
homr.main.process_image(...)
        |
        v
temp_score.musicxml
        |
        v
music21 converter
        |
        v
temp_score.mid
        |
        v
QDrag / QMimeData URL drag into DAW
```

## 顶层目录职责

| 路径 | 职责 |
| --- | --- |
| `homr_gui.py` | GPU 优先的 PyQt6 GUI 入口。监听剪贴板图片，直接调用 HOMR 引擎，生成 MIDI 并支持拖拽。 |
| `homr_gui_cpu.py` | CPU 兼容模式 GUI 入口。逻辑几乎与 GPU 入口相同，但强制 `use_gpu_inference=False`，并在处理前下载缺失的 CPU ONNX 权重。 |
| `启动.bat` | Windows 无控制台启动脚本，使用 `python_embed\pythonw.exe homr_gui.py`。 |
| `CPU兼容模式.bat` | Windows CPU 安全模式启动脚本，使用 `python_embed\python.exe homr_gui_cpu.py`，保留控制台便于看错误。 |
| `调试启动.bat` | Windows 调试启动脚本，运行 GPU GUI 入口并暂停控制台。 |
| `homr/` | 运行时 OMR 引擎。包含图片预处理、分割模型推理、谱表检测、Transformer 识别、MusicXML 生成、ONNX Runtime 封装。 |
| `training/` | 训练、数据集转换、ONNX 导出和量化代码。运行 GUI 时不走这里。 |
| `validation/` | 识别结果评估脚本。 |
| `tests/` | 上游核心逻辑测试，覆盖解析、检测、MusicXML、数据集转换等。 |
| `docs/` | Sphinx 文档目录。当前 `docs/source/libs.rst` 仍指向模板里的 `libs` 包，属于遗留配置。 |
| `requirements.txt` / `pyproject.toml` | Python 依赖。这个 fork 新增了 GUI 和 MIDI 转换所需的 `pyqt6`、`music21`。 |

## 运行时分层

### 1. GUI 表示层

入口：`homr_gui.py`、`homr_gui_cpu.py`

核心类：

| 类/函数 | 职责 |
| --- | --- |
| `HomrGui` | PyQt6 窗口、无边框置顶 UI、状态切换、剪贴板监听、拖拽输出。 |
| `WorkerThread` | 后台处理线程，避免图像识别阻塞 UI 线程。 |
| `CFG` | UI 尺寸、字体、颜色、状态文案集中配置。 |

GUI 的状态机很小：

| 状态 | 触发条件 | UI 含义 |
| --- | --- | --- |
| `idle` | 启动后或初始状态 | 等待用户用 `Win + Shift + S` 截图到剪贴板。 |
| `processing` | 发现新的剪贴板图片后 | 保存 `temp_score.png`，后台运行 OMR。 |
| `success` | 生成 `.mid` 文件后 | 主按钮可拖拽当前 MIDI 文件。 |
| `error` | 识别、XML 生成或 MIDI 转换失败 | 提示用户重新截图。 |

剪贴板处理使用 `QApplication.clipboard().dataChanged`，再通过 `QTimer.singleShot(250, ...)` 做 250ms 延迟，避免同一次截图触发多次处理。`QImage.cacheKey()` 用于跳过重复图片。

### 2. GUI 编排层

`WorkerThread.run()` 是 GUI 和 HOMR 引擎之间的连接点：

1. 选择推理模式：
   - `homr_gui.py`：`use_gpu_inference=True`
   - `homr_gui_cpu.py`：`use_gpu_inference=False`
2. 构造 `ProcessingConfig`：
   - `enable_debug=False`
   - `enable_cache=False`
   - 不读写 staff position
   - `selected_staff=-1`，处理全部谱表
3. 构造 `XmlGeneratorArguments(False, None, None)`，即不额外写大页面、节拍器或 tempo。
4. 直接调用 `homr.main.process_image(self.img_path, config, xml_args)`。
5. 如果生成了同名 `.musicxml`，用 `music21.converter.parse()` 读取，再 `score.write("midi", fp=out_mid)` 输出 `.mid`。
6. 通过 Qt signal 把成功或失败结果发回 UI 线程。

这个实现避免了再启动一个 `poetry run homr ...` 或 `python -m homr.main ...` 子进程，因此模型和 `music21` 可以在当前进程内复用。代码注释里也把这点称为“消除冷启动”。

### 3. HOMR 应用服务层

入口：`homr/main.py`

`process_image()` 是运行时核心 API。CLI 和 GUI 都可以复用它。它负责把一张图片转换成同路径 `.musicxml`：

1. 读取输入图片。
2. 如果配置为读取已有 staff position，则从 `.txt` 恢复谱表位置。
3. 否则调用 `detect_staffs_in_image()` 运行完整检测流程。
4. 为 Transformer 构造 `Config()`，把 `config.use_gpu_inference` 透传进去。
5. 调用 `parse_staffs()` 逐行识别谱表符号。
6. 等待标题 OCR 的 `Future`，拿到曲名。
7. 调用 `generate_xml()` 把符号序列写成 MusicXML。
8. 写 `_teaser.png`，并清理上一次残留的 debug 文件。
9. 发生异常时删除半成品 `.musicxml`。

CLI 的 `main()` 在调用 `process_image()` 前会执行 `download_weights(use_gpu_inference)`。当前 CPU GUI 也显式调用了 `download_weights(False)`，但 GPU GUI 没有显式调用 `download_weights(True)`，因此 GPU 入口目前更依赖模型文件已经存在。

### 4. 图像预处理和分割层

主要文件：

| 文件 | 职责 |
| --- | --- |
| `homr/autocrop.py` | 自动裁剪输入图片。 |
| `homr/resize.py` | 调整输入图片尺寸。 |
| `homr/color_adjust.py` | 使用 CLAHE 做局部对比度增强。 |
| `homr/segmentation/inference_segnet.py` | 运行 SegNet ONNX 模型，输出分割 mask。 |
| `homr/noise_filtering.py` | 对分割结果做噪声过滤。 |

分割模型输出被拆成几个二值 mask：

| mask | 后续用途 |
| --- | --- |
| `staff` | 五线谱线段检测和谱表重建。 |
| `symbols` | 通用符号、连谱号/括号等辅助检测。 |
| `stems_rests` | 符干、休止符、候选小节线。 |
| `notehead` | 音符头椭圆检测。 |
| `clefs_keys` | 谱号和调号，作为 staff anchor。 |

`Segnet` 会根据 `use_gpu_inference` 选择 fp16 GPU 模型或 CPU 模型。当前 fork 把 ONNX Runtime session 创建统一改成 `homr.onnxruntime_utils.create_inference_session()`。

### 5. 几何检测和谱表结构层

主要文件：

| 文件 | 职责 |
| --- | --- |
| `homr/bounding_boxes.py` | 从 mask 提取旋转框、椭圆框，提供重叠和绘制工具。 |
| `homr/note_detection.py` | 合并 notehead 和 stem，把音符挂到谱表上。 |
| `homr/bar_line_detection.py` | 从候选竖线中过滤小节线。 |
| `homr/staff_detection.py` | 根据 staff fragments、clefs、bar lines 重建五线谱。 |
| `homr/brace_dot_detection.py` | 检测大括号、括号和 grand staff 连接关系。 |
| `homr/model.py` | `StaffPoint`、`Staff`、`MultiStaff`、`Note`、`BarLine` 等核心领域对象。 |

`detect_staffs_in_image()` 的关键步骤：

1. 把分割 mask 转成几何 bounding boxes。
2. 合并音符头和符干，估算平均音符头高度。
3. 检测小节线。
4. 使用 staff fragments、谱号/调号、小节线作为锚点重建谱表。
5. 异步启动标题 OCR。
6. 检测连谱号和括号，把相关谱表合并成 `MultiStaff`。
7. 把 notes 分配到谱表。

### 6. 谱表识别和 MusicXML 层

主要文件：

| 文件 | 职责 |
| --- | --- |
| `homr/staff_parsing.py` | 裁剪、去弯曲、归一化每个谱表，并调用 TrOMR。 |
| `homr/staff_dewarping.py` | 透视/弯曲校正。 |
| `homr/staff_parsing_tromr.py` | 缓存并调用 `Staff2Score`。 |
| `homr/transformer/staff2score.py` | Transformer 推理门面，包含 encoder 和 decoder。 |
| `homr/transformer/encoder_inference.py` | ONNX encoder 推理。 |
| `homr/transformer/decoder_inference.py` | ONNX decoder 自回归生成符号序列。 |
| `homr/transformer/vocabulary.py` | 符号 token、`EncodedSymbol`、去重等逻辑。 |
| `homr/music_xml_generator.py` | 把 `EncodedSymbol` 序列转换为 MusicXML。 |

`parse_staffs()` 会把每个 `Staff` 准备成固定画布尺寸的图片，调用 TrOMR 得到 `EncodedSymbol` 序列。非 grand staff 会过滤掉 `position == "lower"` 的结果，避免单谱表误带 lower staff 信息。识别完成后，`generate_xml()` 按 part、measure、note/rest、barline、clef、key/time signature 等规则组织成 MusicXML。

### 7. 模型和运行时基础设施

主要文件：

| 文件 | 职责 |
| --- | --- |
| `homr/onnxruntime_utils.py` | 当前 fork 新增的 ONNX Runtime provider 封装。 |
| `homr/download_utils.py` | 下载和解压模型 zip/tar。 |
| `homr/main.py::download_weights()` | 下载 SegNet、Transformer encoder、Transformer decoder 权重。 |
| `homr/title_detection.py` | RapidOCR 标题检测，当前 fork 支持按 GPU/CPU 初始化 OCR。 |
| `training/onnx/main.py` | 从训练 checkpoint 导出、简化、量化 ONNX 模型。 |

`onnxruntime_utils.py` 统一了这些事情：

1. `preload_cuda_dlls()`：预加载 CUDA/cuDNN DLL，面向 Windows 嵌入式 Python 场景。
2. `execution_providers()`：GPU 可用时返回 `CUDAExecutionProvider` 加 `CPUExecutionProvider`，否则只返回 CPU。
3. `create_inference_session()`：创建 ONNX session，GPU 创建失败时记录错误并降级 CPU。
4. `rapidocr_params()`：把同一套 GPU/CPU 判定传给 RapidOCR。
5. `log_onnxruntime_status()`：输出 ORT 版本、设备和 provider 状态。

## 当前对 HOMR 的包装和功能

| 功能 | 用户侧表现 | 实现思路 |
| --- | --- | --- |
| 图形化入口 | 不需要命令行输入图片路径。 | 用 PyQt6 `QWidget` 做一个小型置顶无边框窗口，主按钮承担状态提示和拖拽入口。 |
| 截图即输入 | 用户用系统截图工具把乐谱放进剪贴板后自动识别。 | 监听 `QClipboard.dataChanged`，读取 `mimeData.hasImage()`，保存为工作目录下 `temp_score.png`。 |
| 后台识别 | UI 不会在模型推理时卡死。 | `WorkerThread(QThread)` 中调用 `process_image()`，成功/失败通过 signal 回 UI。 |
| 直接复用 HOMR 引擎 | 不再 shell 出 CLI 子进程。 | 导入 `homr.main.process_image` 和 `ProcessingConfig`，在进程内调用。 |
| GPU 模式 | 默认入口请求 CUDA 加速。 | `homr_gui.py` 设置 `use_gpu_inference=True`，底层通过 ONNX Runtime provider 尝试 CUDA，失败时部分 session 会降级 CPU。 |
| CPU 兼容模式 | 为没有 CUDA 的机器提供更稳妥入口。 | `homr_gui_cpu.py` 设置 `use_gpu_inference=False`，并在处理前调用 `download_weights(False)` 下载 CPU 权重。 |
| MusicXML 转 MIDI | 最终给用户 `.mid`，而不是只给 `.musicxml`。 | HOMR 生成 MusicXML 后，用 `music21.converter.parse()` 读取，再 `score.write("midi", fp=...)` 导出。 |
| 拖入 DAW | 转换成功后按住主按钮可拖出 MIDI 文件。 | `QDrag` + `QMimeData.setUrls([QUrl.fromLocalFile(self.current_output)])`。 |
| 状态反馈 | 主按钮在等待、处理中、成功、失败时显示不同文案和颜色。 | `CFG["STATES"]` 定义状态样式，`_apply_state()` 更新按钮文本、背景和阴影。 |
| Windows 启动脚本 | 双击 `.bat` 启动普通、CPU、调试模式。 | 批处理脚本固定调用 `python_embed` 下的 Python 解释器和对应入口文件。 |
| ONNX Runtime 稳定性改造 | 减少 CUDA provider 初始化失败导致的直接崩溃。 | 把上游分散在各模型里的 ORT 初始化逻辑抽到 `homr/onnxruntime_utils.py`，各模型统一使用。 |

## 相对上游 HOMR 的主要改动点

### 新增 GUI 和交付工作流

上游 HOMR 的主要使用方式是 `uvx homr <img>` 或 `poetry run homr <image>`，输出同路径 MusicXML。这个 fork 新增了：

- `homr_gui.py`
- `homr_gui_cpu.py`
- `启动.bat`
- `CPU兼容模式.bat`
- `调试启动.bat`
- `requirements.txt`
- README 中的 GUI 说明

同时在依赖中加入：

- `pyqt6`：桌面 GUI。
- `music21`：MusicXML 到 MIDI 的转换。

### ONNX Runtime provider 抽象

上游代码在 SegNet、Transformer encoder、Transformer decoder、CLI 里直接调用 `onnxruntime`。当前 fork 新增 `homr/onnxruntime_utils.py`，并改动了这些调用点：

- `homr/main.py`
- `homr/segmentation/inference_segnet.py`
- `homr/transformer/encoder_inference.py`
- `homr/transformer/decoder_inference.py`
- `homr/title_detection.py`

这让 CUDA 可用性检测、DLL 预加载、日志输出、GPU 失败降级和 RapidOCR 参数保持一致。

### 标题 OCR 支持 GPU/CPU 参数传递

`homr/title_detection.py` 的 `detect_title()` 现在接收 `use_gpu_inference`，并通过 `rapidocr_params()` 初始化 RapidOCR。`homr/main.py` 在调用 `detect_title()` 和 `download_ocr_weights()` 时也透传这个标志。

### 文档中提到但代码未完全体现的点

README 写到“国内优化：优化了模型下载逻辑，使用镜像代理提升下载速度”。但当前工作区中 `homr/main.py::download_weights()` 的 `base_url` 仍是：

```text
https://github.com/liebharc/homr/releases/download/onnx_checkpoints/
```

没有看到镜像代理或可配置下载源实现。后续如果要把这个作为正式功能，需要补齐配置项、README 和错误处理。

## 重要开发注意事项

1. `homr_gui.py` 和 `homr_gui_cpu.py` 大量重复。现在二者的主要差别是 `use_gpu_inference` 和 CPU 模式的 `download_weights(False)`。如果继续扩展 GUI，建议先抽公共模块，避免双份改动漂移。
2. GPU GUI 当前没有像 CLI 和 CPU GUI 那样显式调用 `download_weights(True)`。如果模型文件不存在，GPU 首次运行可能直接失败。
3. GUI 固定使用工作目录下的 `temp_score.png`、`temp_score.musicxml`、`temp_score.mid`。连续多次截图会覆盖上一轮输出；如果需要保留历史结果，应改成带时间戳或内容 hash 的文件名。
4. GUI 配置里 `enable_cache=False`、`enable_debug=False`，因此不会复用 `.npy` 分割缓存，也不会保留中间 debug 图。排查识别质量问题时可能需要给 GUI 加开关。
5. `docs/source/libs.rst` 仍指向 `libs` 包，而当前仓库没有这个包。Sphinx API 文档配置需要后续清理或改成 `homr`。
6. `training/` 和 `validation/` 是模型研发和评估路径，GUI 日常运行不依赖它们。修改运行时行为时优先看 `homr/` 和 GUI 入口。

## 接手修改时的推荐阅读顺序

1. `homr_gui.py` 或 `homr_gui_cpu.py`：理解桌面工作流。
2. `homr/main.py::process_image()`：理解 HOMR 引擎的主调用链。
3. `homr/segmentation/inference_segnet.py`：理解第一阶段 mask 预测。
4. `homr/staff_detection.py`、`homr/note_detection.py`、`homr/brace_dot_detection.py`：理解几何结构恢复。
5. `homr/staff_parsing.py`、`homr/transformer/staff2score.py`：理解每条谱表如何送入 Transformer。
6. `homr/music_xml_generator.py`：理解输出格式和后续 MIDI 转换的输入。
7. `homr/onnxruntime_utils.py`：理解 CPU/GPU provider、降级和 OCR 参数。
