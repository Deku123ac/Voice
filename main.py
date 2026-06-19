import sys


DEPENDENCY_MESSAGE = (
    "Thiếu thư viện. Hãy chạy run.bat hoặc install.bat."
)


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        from app.gui import MainWindow
    except ImportError as exc:
        print(DEPENDENCY_MESSAGE)
        print(f"Chi tiết: {exc}")
        try:
            from app.error_logger import log_exception

            log_exception("main.import", exc)
        except ImportError:
            print("Không thể nạp bộ ghi log vì dependency chưa đầy đủ.")
        return 1

    try:
        app = QApplication(sys.argv)
        app.setApplicationName("Dani-like Auto TTS Studio")
        window = MainWindow()
        window.show()
        return app.exec()
    except Exception as exc:
        from app.error_logger import log_exception

        log_exception("main.main", exc)
        try:
            QMessageBox.critical(
                None,
                "Lỗi khởi động",
                f"{DEPENDENCY_MESSAGE}\n\nChi tiết: {exc}",
            )
        except Exception:
            print(f"{DEPENDENCY_MESSAGE}\nChi tiết: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
