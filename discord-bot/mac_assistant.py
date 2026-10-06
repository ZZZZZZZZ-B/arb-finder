"""On-demand macOS region capture. Run with python mac_assistant.py."""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from discord_bot import DEFAULT_MODEL, BotSettings, RequestStats, build_payload, image_data_url, request_answer


@dataclass(frozen=True)
class Region:
    screen_name: str
    x: int
    y: int
    width: int
    height: int

    def valid_for(self, width: int, height: int) -> bool:
        return (
            isinstance(self.screen_name, str)
            and all(type(value) is int for value in (self.x, self.y, self.width, self.height))
            and self.x >= 0 and self.y >= 0 and self.width > 0 and self.height > 0
            and self.x + self.width <= width and self.y + self.height <= height
        )


def api_settings() -> BotSettings:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("请在启动前设置 OPENROUTER_API_KEY")
    # Local assistant does not log in to Discord or require Discord credentials.
    return BotSettings("", key, 1, model=os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL))


def main() -> None:
    if sys.platform != "darwin":
        raise SystemExit("此助手仅支持 macOS")
    from PySide6 import QtCore, QtGui, QtWidgets
    from pynput import keyboard

    settings = api_settings()
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    stats = RequestStats(os.getenv("MAC_STATS_DB", "output/mac_stats.sqlite3"))
    region_path = Path("output/mac_region.json")
    executor = ThreadPoolExecutor(max_workers=1)

    class Signals(QtCore.QObject):
        trigger = QtCore.Signal()
        result = QtCore.Signal(str)

    signals = Signals()

    class Selector(QtWidgets.QWidget):
        def __init__(self, screen):
            super().__init__()
            self.target_screen = screen
            self.start = None
            self.selection = QtCore.QRect()
            self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
            self.setGeometry(screen.geometry())
            self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
            self.setCursor(QtCore.Qt.CrossCursor)
            self.band = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self)

        def paintEvent(self, event):
            painter = QtGui.QPainter(self)
            painter.fillRect(self.rect(), QtGui.QColor(20, 20, 20, 100))
            painter.setPen(QtCore.Qt.white)
            painter.drawText(24, 40, "拖动框选题目区域；Esc 取消。选区不需要包含 True/False 按钮。")

        def mousePressEvent(self, event):
            if event.button() == QtCore.Qt.LeftButton:
                self.start = event.position().toPoint()
                self.band.setGeometry(QtCore.QRect(self.start, QtCore.QSize()))
                self.band.show()

        def mouseMoveEvent(self, event):
            if self.start is not None:
                self.selection = QtCore.QRect(self.start, event.position().toPoint()).normalized()
                self.band.setGeometry(self.selection)

        def mouseReleaseEvent(self, event):
            if self.start is None:
                return
            self.selection = QtCore.QRect(self.start, event.position().toPoint()).normalized().intersected(self.rect())
            r = self.selection
            if r.width() >= 20 and r.height() >= 20:
                window.region = Region(self.target_screen.name(), r.x(), r.y(), r.width(), r.height())
                try:
                    region_path.parent.mkdir(parents=True, exist_ok=True)
                    region_path.write_text(json.dumps(vars(window.region)), encoding="utf-8")
                    window.status.setText("区域已保存；按 ⌥ Space 判断")
                except OSError:
                    window.status.setText("区域已选择，但无法保存；本次启动仍可使用")
            self.close()
            window.show()

        def keyPressEvent(self, event):
            if event.key() == QtCore.Qt.Key_Escape:
                self.close()
                window.show()

    class Assistant(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.region = None
            self.selector = None
            self.busy = False
            self.paused = False
            self.setWindowTitle("截图判断助手")
            self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
            self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
            self.resize(390, 230)
            layout = QtWidgets.QVBoxLayout(self)
            self.status = QtWidgets.QLabel("选择屏幕区域，然后按 ⌥ Space")
            self.status.setWordWrap(True)
            self.answer = QtWidgets.QLabel("—")
            self.answer.setStyleSheet("font-size: 42px; font-weight: bold;")
            layout.addWidget(self.status)
            layout.addWidget(self.answer)
            for label, callback in [("框选区域（鼠标所在屏幕）", self.select_region),
                                    ("立即判断", self.capture), ("暂停 / 恢复", self.pause),
                                    ("统计", self.show_stats), ("退出", app.quit)]:
                button = QtWidgets.QPushButton(label)
                button.clicked.connect(callback)
                layout.addWidget(button)
            try:
                saved = Region(**json.loads(region_path.read_text(encoding="utf-8")))
                if saved.valid_for(100000, 100000):
                    self.region = saved
            except (OSError, TypeError, ValueError):
                pass
            signals.trigger.connect(self.capture)
            signals.result.connect(self.completed)

        def select_region(self):
            if self.busy:
                return
            screen = app.screenAt(QtGui.QCursor.pos()) or app.primaryScreen()
            self.hide()
            self.selector = Selector(screen)
            self.selector.show()
            self.selector.activateWindow()

        def pause(self):
            self.paused = not self.paused
            self.status.setText("已暂停" if self.paused else "已恢复；按 ⌥ Space 判断")

        def show_stats(self):
            QtWidgets.QMessageBox.information(self, "统计", stats.render())

        def capture(self):
            if self.busy or self.paused or (self.selector is not None and self.selector.isVisible()):
                return
            r = self.region
            screen = next((s for s in app.screens() if r and s.name() == r.screen_name), None)
            if screen is None or not r.valid_for(screen.geometry().width(), screen.geometry().height()):
                self.status.setText("请重新框选区域（屏幕连接或布局可能已变化）")
                return
            # Keep the answer window out of the image before grabbing the screen.
            self.busy = True
            self.hide()
            QtCore.QTimer.singleShot(120, lambda: self.grab(screen, r))

        def grab(self, screen, r):
            try:
                image = screen.grabWindow(0, r.x, r.y, r.width, r.height)
                if image.isNull():
                    raise RuntimeError("截图失败；请检查 macOS 屏幕录制权限")
                # QScreen coordinates are logical; pixmap preserves Retina pixel density.
                data = QtCore.QByteArray()
                buffer = QtCore.QBuffer(data)
                buffer.open(QtCore.QIODevice.WriteOnly)
                if not image.save(buffer, "PNG"):
                    raise RuntimeError("图片编码失败")
                buffer.close()
                payload = build_payload(settings.model, "", image_data_url(bytes(data), "capture.png", "image/png"))
                self.answer.setText("…")
                self.status.setText("判断中…")
                self.show()
                executor.submit(self.query, payload)
            except Exception:
                self.completed("截图失败；请检查屏幕录制权限并重新选择区域")

        def query(self, payload):
            try:
                answer = request_answer(settings, payload, stats)
            except Exception:
                # Do not display raw exceptions: provider errors may include private data.
                answer = "无法判断：请检查网络、API Key 或模型配置"
            signals.result.emit(answer)

        def completed(self, answer):
            self.busy = False
            self.show()
            self.answer.setText(answer if answer in {"True", "False"} else "无法判断")
            self.answer.setStyleSheet(
                "font-size: 42px; font-weight: bold; color: "
                + ("#16a34a" if answer == "True" else "#dc2626" if answer == "False" else "#888888") + ";"
            )
            self.status.setText("按 ⌥ Space 判断下一题" if answer in {"True", "False"} else answer)

        def closeEvent(self, event):
            app.quit()
            event.accept()

    window = Assistant()
    window.show()
    listener = keyboard.GlobalHotKeys({"<alt>+<space>": signals.trigger.emit})
    try:
        listener.start()
        listener.wait()
        if not keyboard.Listener.IS_TRUSTED:
            window.status.setText("全局快捷键缺少辅助功能权限；可先使用立即判断按钮")
    except Exception:
        window.status.setText("全局快捷键启动失败；可使用立即判断按钮")

    def cleanup():
        listener.stop()
        executor.shutdown(wait=False, cancel_futures=True)

    app.aboutToQuit.connect(cleanup)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
