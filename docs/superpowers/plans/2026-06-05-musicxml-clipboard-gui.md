# MusicXML Clipboard GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new `homr_musicxml_gui.py` entry point that converts clipboard screenshots to timestamped `.musicxml` files in a user-selected output folder.

**Architecture:** Keep existing MIDI/DAW GUI files untouched. Put the new workflow in one dedicated file with small pure helper functions for settings and output naming, plus a PyQt6 window and worker thread for clipboard-driven recognition.

**Tech Stack:** Python 3.11+, PyQt6, HOMR `process_image()`, ONNX Runtime helper functions, pytest for pure helper tests.

---

### Task 1: Add Pure Helper Tests

**Files:**
- Create: `tests/test_homr_musicxml_gui.py`
- Later modify: `homr_musicxml_gui.py`

- [ ] **Step 1: Write failing tests for settings and filenames**

Add tests covering:

```python
def test_settings_round_trip(tmp_path):
    settings_path = tmp_path / "settings.json"
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    save_settings(settings_path, output_dir)

    assert load_settings(settings_path).output_dir == output_dir


def test_load_settings_ignores_missing_or_invalid_output_dir(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"output_dir": "/does/not/exist"}')

    assert load_settings(settings_path).output_dir is None


def test_timestamp_output_path_adds_suffix_on_collision(tmp_path):
    first = build_timestamped_output_path(tmp_path, now=datetime(2026, 6, 5, 14, 30, 12))
    first.write_text("existing")

    second = build_timestamped_output_path(tmp_path, now=datetime(2026, 6, 5, 14, 30, 12))

    assert second.name == "homr_20260605_143012_1.musicxml"
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `python3 -m pytest tests/test_homr_musicxml_gui.py -q`

Expected: FAIL because `homr_musicxml_gui` does not exist yet.

### Task 2: Implement `homr_musicxml_gui.py`

**Files:**
- Create: `homr_musicxml_gui.py`

- [ ] **Step 1: Add pure helper functions**

Implement:

- `GuiSettings`
- `load_settings(settings_path: Path) -> GuiSettings`
- `save_settings(settings_path: Path, output_dir: Path) -> None`
- `build_timestamped_output_path(output_dir: Path, now: datetime | None = None) -> Path`
- `move_musicxml_to_output(temp_xml: Path, output_dir: Path) -> Path`

- [ ] **Step 2: Run helper tests**

Run: `python3 -m pytest tests/test_homr_musicxml_gui.py -q`

Expected: PASS.

- [ ] **Step 3: Add PyQt6 GUI shell**

Implement:

- compact always-on-top `HomrMusicXmlGui(QWidget)`
- `选择文件夹` button
- `打开文件夹` button
- clipboard `dataChanged` listener with duplicate-image guard
- idle/processing/success/error states

- [ ] **Step 4: Add worker thread**

Implement `WorkerThread(QThread)` that:

1. Receives image path and output directory.
2. Detects CUDA with `is_cuda_available()`.
3. Calls `download_weights(use_gpu_inference)`.
4. Calls `process_image(image_path, config, xml_args)`.
5. Moves generated temporary `.musicxml` to timestamped output file.
6. Emits final output path.

- [ ] **Step 5: Add folder opening**

Use `QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_dir)))`.

### Task 3: Verify and Review

**Files:**
- Test: `tests/test_homr_musicxml_gui.py`
- Check: `homr_musicxml_gui.py`

- [ ] **Step 1: Run targeted helper tests**

Run: `python3 -m pytest tests/test_homr_musicxml_gui.py -q`

Expected: PASS.

- [ ] **Step 2: Run static import check**

Run: `python3 -m py_compile homr_musicxml_gui.py tests/test_homr_musicxml_gui.py`

Expected: PASS.

- [ ] **Step 3: Review diff**

Run: `git diff -- homr_musicxml_gui.py tests/test_homr_musicxml_gui.py docs/superpowers/plans/2026-06-05-musicxml-clipboard-gui.md`

Expected: only planned files changed.
