# MusicXML Clipboard GUI Design

## Goal

Create a new dedicated GUI entry point, `homr_musicxml_gui.py`, for a lighter HOMR workflow:

1. Accept a sheet-music image from the system clipboard.
2. Run HOMR recognition in the background.
3. Save the generated `.musicxml` file to a user-selected output folder.
4. Use timestamped output filenames.
5. Show the generated filename in the UI.
6. Provide a button that opens the output folder.

The existing `homr_gui.py` and `homr_gui_cpu.py` MIDI/DAW workflow stays untouched.

## Non-Goals

- Do not generate MIDI.
- Do not import or use `music21`.
- Do not support dragging files into a DAW.
- Do not refactor the existing GUI files in this change.
- Do not change HOMR recognition internals unless needed to call the existing API safely.

## Proposed Entry Point

Add one new file:

```text
homr_musicxml_gui.py
```

This file owns the new workflow end to end. It can reuse layout and state styling ideas from `homr_gui.py`, but it should not require users to choose between separate CPU and GPU scripts.

## Inference Mode

Use automatic inference mode:

1. Call `is_cuda_available()` from `homr.onnxruntime_utils`.
2. Set `use_gpu_inference=True` only when CUDA is available.
3. Otherwise use CPU.
4. Before processing, call `download_weights(use_gpu_inference)` so the first run can fetch the matching model set.

This keeps the new tool as a single maintainable entry point.

## Settings

Persist the output folder in a JSON file:

```text
homr_musicxml_gui_settings.json
```

Recommended shape:

```json
{
  "output_dir": "/absolute/path/to/output"
}
```

The file should live next to the script in the project/runtime directory. This is easier to inspect than platform registry-backed settings and fits the current portable Windows `python_embed` setup.

Behavior:

- On startup, read the settings file if it exists.
- If `output_dir` exists, display it or at least keep it active internally.
- If it is missing or invalid, ask the user to select a folder before recognition can start.
- When the user chooses a folder, write the setting immediately.

## UI Behavior

The new GUI keeps the compact always-on-top window style, but changes the workflow text:

| State | Title | Subtitle |
| --- | --- | --- |
| `idle` | `框选乐谱` | `截图后自动识别` or selected folder hint |
| `processing` | `解析中` | `HOMR Engine Running` |
| `success` | `转换成功` | generated `.musicxml` filename |
| `error` | `识别失败` | short retry/error hint |

Add two explicit controls:

1. `选择文件夹`
   - Opens `QFileDialog.getExistingDirectory()`.
   - Persists the selected folder.
2. `打开文件夹`
   - Opens the selected output folder.
   - Disabled when no valid folder is configured.

The primary button no longer starts drag-and-drop. It is only a large status surface.

## Data Flow

```text
Clipboard image
    -> save temporary input image
    -> WorkerThread
    -> download_weights(use_gpu_inference)
    -> process_image(temp_input, config, xml_args)
    -> temp_input.musicxml
    -> timestamped output file in selected output_dir
    -> UI success state with filename
```

`process_image()` currently writes the MusicXML beside the input image. The GUI should keep using that API and move or copy the generated file afterward.

## Output Naming

Use timestamped filenames:

```text
homr_YYYYMMDD_HHMMSS.musicxml
```

If a file already exists, append a numeric suffix:

```text
homr_YYYYMMDD_HHMMSS_1.musicxml
homr_YYYYMMDD_HHMMSS_2.musicxml
```

This avoids overwriting results when users run multiple recognitions quickly.

## Temporary Files

The screenshot input can remain a temporary file. Acceptable options:

- Use a fixed local temporary input such as `temp_score.png`, then overwrite it each run.
- Prefer a private temporary filename if implementation complexity stays low.

The final `.musicxml` must always be copied or moved to the selected output folder with the timestamped name.

## Error Handling

Handle these cases explicitly:

1. Clipboard content is not an image: ignore it.
2. Image is empty/null: ignore it.
3. Output folder is unset or invalid: prompt for a folder before starting recognition.
4. User cancels folder selection: return to idle and do not process.
5. HOMR fails: show `识别失败` and log the traceback to console.
6. HOMR finishes but no temporary `.musicxml` exists: show an error.
7. Opening the output folder fails: show an error or log it; do not lose the converted file.

## Implementation Notes

- Keep recognition in a `QThread` so UI remains responsive.
- Emit the final output path from the worker on success.
- Store `current_output_file` for display, but do not drag it.
- Remove unused imports from this new file: `music21`, `QDrag`, `QMimeData`, `QUrl`.
- Use `QDesktopServices.openUrl(QUrl.fromLocalFile(output_dir))` for opening the folder, or a small platform helper if this fails in the target runtime.

## Validation

Minimum checks:

1. Static import check for `homr_musicxml_gui.py`.
2. Unit-testable helper behavior if extracted:
   - settings load/save
   - timestamp filename collision handling
3. Manual smoke path:
   - start GUI
   - choose output folder
   - copy a music-score image to clipboard
   - wait for success
   - confirm `.musicxml` exists in selected folder
   - click open-folder button

Full HOMR recognition may require model downloads and ONNX runtime dependencies, so the implementation should separate pure helper tests from model-dependent smoke testing.
