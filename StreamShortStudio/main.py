import sys, json, traceback
from pathlib import Path
from studio.runtime import data_dir

def log_error(exc_type,exc,tb):
    message=''.join(traceback.format_exception(exc_type,exc,tb))
    try:(data_dir()/'error.log').write_text(message,encoding='utf-8')
    except OSError:pass
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app=QApplication.instance() or QApplication([])
        QMessageBox.critical(None,'StreamShort Studio',f'프로그램 실행 중 오류가 발생했습니다.\n{exc}\n\nZIP 전체를 압축 해제했는지 확인하세요. Data/error.log에 상세 내용을 기록합니다.')
    except Exception:
        if sys.platform=='win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0,'ZIP 전체를 다시 압축 해제하세요.\n'+str(exc),'StreamShort Studio',0x10)

def main():
    if len(sys.argv)>1 and sys.argv[1]=='--self-test':
        from studio.selftest import run_selftest
        return run_selftest(Path(sys.argv[2]),require_frozen='--require-frozen' in sys.argv)
    sys.excepthook=log_error
    from studio.ui import run
    try:return run()
    except Exception:
        log_error(*sys.exc_info());return 1

if __name__=='__main__':raise SystemExit(main())
