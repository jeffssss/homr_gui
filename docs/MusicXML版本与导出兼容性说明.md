# MusicXML 版本与导出兼容性说明

本文档记录当前项目关于 MusicXML 版本、模型输出和导出兼容性的结论，避免把“模型识别能力”和“最终 XML 文件声明版本”混为一谈。

## 当前项目生成的 MusicXML 版本

当前项目生成的是 `score-partwise` 形式的 **MusicXML 4.0**。

核心代码在 `homr/music_xml_generator.py`：

```python
root = mxl.XMLScorePartwise(version="4.0")
```

GUI 入口不会单独决定 MusicXML 版本。`homr_musicxml_gui.py` 只是调用 `process_image()`，最终由 `homr/main.py` 调用 `generate_xml()`，再把结果写成 `.musicxml` 文件。

需要注意：`requirements.txt` 和 `pyproject.toml` 中的 `musicxml==1.4` 是 Python 依赖包版本，不是导出的 MusicXML 规范版本。

## MusicXML 的主要版本

MusicXML 主要历史版本包括：

| 版本 | 发布时间 | 说明 |
| --- | --- | --- |
| 1.0 | 2004-01 | 初始正式版本 |
| 1.1 | 2005-05 | 历史正式版本 |
| 2.0 | 2007-06 | 引入压缩 MusicXML 容器等能力 |
| 3.0 | 2011-08 | 较长时间内常见的兼容目标 |
| 3.1 | 2017-12 | 常见现代兼容目标，推荐未压缩文件使用 `.musicxml` 扩展名 |
| 4.0 | 2021-06 | 当前正式 Final Report |
| 4.1 | 2025-04 Draft | 草案版本，不建议作为稳定默认导出目标 |

官方资料：

- [MusicXML 4.0 Final Community Group Report](https://www.w3.org/2021/06/musicxml40/)
- [MusicXML 4.1 Draft](https://w3c-cg.github.io/musicxml/)
- [MusicXML version history](https://w3c-cg.github.io/musicxml/version-history/)

## 常见或值得支持的版本

实际工程上，最值得关注的是：

| 版本 | 建议 |
| --- | --- |
| 4.0 | 推荐默认导出目标。当前项目已经使用它。 |
| 3.1 | 推荐作为兼容导出目标，适合需要兼容较旧软件的场景。 |
| 3.0 | 可作为旧软件兼容目标，但优先级低于 3.1。 |
| 2.0 | 仅在明确需要兼容特定老软件时考虑。 |
| 1.0 / 1.1 | 基本属于历史兼容目标，不建议新增为常规选项。 |

如果目标是“现代软件尽量都能打开”，优先支持 4.0 和 3.1 通常就够实用。

## 模型输出不是 MusicXML 4.0 文本

HOMR 的模型不是直接识别成 MusicXML XML 文本，也不是严格意义上的“MusicXML 4.0 模型”。

模型输出的是项目自己的中间 token，也就是 `EncodedSymbol`。例如：

```text
clef_G2 . . . upper
keySignature_0 . . . .
timeSignature/4 . . . .
note_4 D5 # accent upper
barline . . . .
```

这些 token 描述的是音乐语义，包括音符、时值、音高、升降号、谱号、小节线、连音和装饰等。最后一步才由 `homr/music_xml_generator.py` 把这些 token 序列化成 MusicXML。

因此更准确的分层是：

```text
截图 / 乐谱图片
        |
        v
HOMR 图像识别和 Transformer
        |
        v
EncodedSymbol token 序列
        |
        v
MusicXML 生成器
        |
        v
.musicxml 文件
```

模型真正受限的是训练词表和训练数据中出现过的音乐符号组合，而不是 MusicXML 根节点声明的版本号。

## 只修改 version 属性意味着什么

把：

```python
root = mxl.XMLScorePartwise(version="4.0")
```

改成：

```python
root = mxl.XMLScorePartwise(version="3.1")
```

通常只会改变导出文件根节点里的版本声明：

```xml
<score-partwise version="3.1">
```

这不会自动改变后续生成的元素、属性和结构。也就是说：

- 识别结果仍然是同一批 `EncodedSymbol`。
- 生成器仍然按当前代码逻辑写 MusicXML。
- 文件只是声明成了 `3.1`。
- 如果输出内容全部属于 3.1 支持范围，那么它可以是有效的 3.1 文件。
- 如果输出内容包含 4.0 才支持的元素或属性，那么它就是“声明为 3.1，但内容不严格符合 3.1”的文件。

所以，只改 `version` 属性不能等同于“严格支持某个 MusicXML 版本”。

## 当前项目降到 3.1 的可行性

当前生成器输出的内容主要是较基础的 MusicXML 结构，例如：

- `score-partwise`
- `part-list`
- `part`
- `measure`
- `attributes`
- `clef`
- `key`
- `time`
- `note`
- `duration`
- `voice`
- `staff`
- `barline`
- `repeat`
- `notations`

这些大多不是 MusicXML 4.0 专属能力。因此，从工程直觉看，支持 3.1 很可能可行。

但“很可能可行”不等于“严格合法”。要宣称支持 3.1，仍然需要用 MusicXML 3.1 对应的 schema 或 DTD 校验实际导出的文件。

## 如果要支持导出多个版本

可以实现，但应该分层处理。

### 最小实现

增加一个导出版本参数，例如 `3.1` / `4.0`，把当前写死的 `version="4.0"` 改成可配置。

这种实现成本低，但只能表示“声明版本可选”，不能保证严格兼容。

### 严谨实现

严谨支持某个版本至少需要：

1. 在 `XmlGeneratorArguments` 或新的导出配置中加入 `musicxml_version`。
2. 在 GUI 中提供版本选择，默认仍使用 `4.0`。
3. 在生成器中按目标版本过滤或降级不兼容的元素和属性。
4. 为每个声明支持的版本准备对应的校验流程。
5. 增加测试样例，确认同一份识别 token 可以导出为目标版本并通过对应校验。

推荐路线：

1. 先支持 `4.0` 和 `3.1`。
2. 默认仍为 `4.0`。
3. `3.1` 标记为兼容导出目标。
4. 不把 `4.1` 作为默认或稳定选项，因为它目前仍是草案。

## 结论

当前项目不是“模型只能识别 MusicXML 4.0”。模型识别的是音乐符号 token，MusicXML 版本是最后导出层的格式声明和兼容性约束。

`root = mxl.XMLScorePartwise(version="4.0")` 中的 `version` 只决定导出文件声明的 MusicXML 版本。要真正支持其他版本，必须让生成内容也符合对应版本的规范，并用对应版本的 schema 或 DTD 做校验。
