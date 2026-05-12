from __future__ import annotations

from typing import Any

import onnxruntime as ort

from homr.simple_logging import eprint

CUDA_EP = "CUDAExecutionProvider"
CPU_EP = "CPUExecutionProvider"

ProviderSpec = str | tuple[str, dict[str, Any]]

_DLLS_PRELOADED = False
_RUNTIME_STATUS_LOGGED = False


def preload_cuda_dlls() -> None:
    """
    Preload CUDA/cuDNN DLLs from bundled NVIDIA packages when available.
    This is especially useful for embedded Python distributions on Windows.
    """
    global _DLLS_PRELOADED  # noqa: PLW0603
    if _DLLS_PRELOADED:
        return

    try:
        ort.preload_dlls(directory="")
    except Exception as exc:
        eprint(f"ONNX Runtime CUDA DLL preload failed: {exc}")
    finally:
        _DLLS_PRELOADED = True


def get_available_providers() -> list[str]:
    preload_cuda_dlls()
    return list(ort.get_available_providers())


def is_cuda_available() -> bool:
    return ort.get_device() == "GPU" and CUDA_EP in get_available_providers()


def configure_onnxruntime_logging(enable_debug: bool = False) -> None:
    ort.set_default_logger_severity(2 if enable_debug else 3)


def cuda_provider_options(
    device_id: int = 0, cudnn_conv_algo_search: str | None = None
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "device_id": device_id,
        "do_copy_in_default_stream": True,
    }
    if cudnn_conv_algo_search is not None:
        options["cudnn_conv_algo_search"] = cudnn_conv_algo_search
    return options


def execution_providers(
    use_gpu_inference: bool,
    device_id: int = 0,
    cuda_options: dict[str, Any] | None = None,
) -> list[ProviderSpec]:
    if use_gpu_inference and is_cuda_available():
        cuda_provider: ProviderSpec = CUDA_EP
        if cuda_options is not None:
            cuda_provider = (CUDA_EP, {"device_id": device_id, **cuda_options})
        return [cuda_provider, CPU_EP]
    return [CPU_EP]


def rapidocr_params(use_gpu_inference: bool, device_id: int = 0) -> dict[str, Any]:
    use_cuda = use_gpu_inference and is_cuda_available()
    return {
        "Global.log_level": "warning",
        "EngineConfig.onnxruntime.use_cuda": use_cuda,
        "EngineConfig.onnxruntime.cuda_ep_cfg.device_id": device_id,
        "EngineConfig.onnxruntime.cuda_ep_cfg.do_copy_in_default_stream": True,
    }


def create_inference_session(
    model_path: str,
    use_gpu_inference: bool,
    component_name: str,
    sess_options: ort.SessionOptions | None = None,
    device_id: int = 0,
    cuda_options: dict[str, Any] | None = None,
) -> tuple[ort.InferenceSession, bool]:
    providers = execution_providers(use_gpu_inference, device_id, cuda_options)
    try:
        session = ort.InferenceSession(
            model_path,
            sess_options=sess_options,
            providers=providers,
        )
    except Exception as exc:
        if not use_gpu_inference:
            raise

        eprint(f"{component_name}: CUDA session failed, retrying with CPUExecutionProvider")
        eprint(exc)
        session = ort.InferenceSession(
            model_path,
            sess_options=sess_options,
            providers=[CPU_EP],
        )
        return session, False

    session_providers = session.get_providers()
    uses_cuda = bool(session_providers and session_providers[0] == CUDA_EP)
    if use_gpu_inference and not uses_cuda:
        eprint(
            f"{component_name}: CUDAExecutionProvider was requested but session providers are "
            f"{session_providers}; running this model on CPU."
        )
    return session, uses_cuda


def log_onnxruntime_status(use_gpu_inference: bool, once: bool = True) -> None:
    global _RUNTIME_STATUS_LOGGED  # noqa: PLW0603
    if once and _RUNTIME_STATUS_LOGGED:
        return

    _RUNTIME_STATUS_LOGGED = True
    providers = get_available_providers()
    cuda_available = is_cuda_available()
    eprint(
        f"ONNX Runtime {ort.__version__}; device={ort.get_device()}; "
        f"available providers={providers}"
    )
    if use_gpu_inference and cuda_available:
        eprint("CUDA acceleration enabled via CUDAExecutionProvider.")
    elif use_gpu_inference:
        eprint("CUDA was requested, but CUDAExecutionProvider is unavailable; using CPU fallback.")
    else:
        eprint("CUDA acceleration disabled; using CPUExecutionProvider.")
