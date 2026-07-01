import sys

from waybill_ocr.cli import main as cli_main
from waybill_ocr.ui.main_window import MainWindow


def run(argv: list[str] | None = None) -> int | None:
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        return cli_main(args)

    window = MainWindow()
    window.run()
    return None
