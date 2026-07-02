from collections.abc import Callable
from dataclasses import dataclass
from importlib.util import find_spec

from waybill_ocr.config import AppConfig

DependencyChecker = Callable[[str], bool]


@dataclass(frozen=True)
class DiagnosticResult:
    name: str
    ok: bool
    message: str


def inspect_environment(
    config: AppConfig,
    dependency_checker: DependencyChecker | None = None,
) -> list[DiagnosticResult]:
    checker = dependency_checker or _is_dependency_available
    return [
        _check_dependency("Pillow", "PIL", checker),
        _check_dependency("pdf2image", "pdf2image", checker),
        _check_tesseract(config),
        _check_poppler(config),
    ]


def format_diagnostic_messages(results: list[DiagnosticResult]) -> list[str]:
    return [f"[{'OK' if result.ok else '缺失'}] {result.message}" for result in results]


def _is_dependency_available(module_name: str) -> bool:
    return find_spec(module_name) is not None


def _check_dependency(display_name: str, module_name: str, checker: DependencyChecker) -> DiagnosticResult:
    if checker(module_name):
        return DiagnosticResult(name=display_name, ok=True, message=f"{display_name} 可用")

    return DiagnosticResult(name=display_name, ok=False, message=f"缺少 {display_name} 依赖，请安装 requirements.txt。")


def _check_tesseract(config: AppConfig) -> DiagnosticResult:
    if config.tesseract_cmd and config.tesseract_cmd.exists():
        return DiagnosticResult(name="Tesseract", ok=True, message="Tesseract 可用")

    return DiagnosticResult(
        name="Tesseract",
        ok=False,
        message="未找到 Tesseract，请放置 tools/tesseract/tesseract.exe 或设置 WAYBILL_OCR_TESSERACT_CMD。",
    )


def _check_poppler(config: AppConfig) -> DiagnosticResult:
    if config.poppler_path and (config.poppler_path / "pdftoppm.exe").exists():
        return DiagnosticResult(name="Poppler", ok=True, message="Poppler 可用")

    return DiagnosticResult(
        name="Poppler",
        ok=False,
        message="未找到 Poppler，请放置 tools/poppler/pdftoppm.exe 或设置 WAYBILL_OCR_POPPLER_PATH。",
    )
