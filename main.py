import sys
import os
import tempfile
import zipfile
import subprocess
import multiprocessing
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QPushButton, QLabel, QFileDialog, QTextEdit, 
                             QMessageBox, QGroupBox, QHBoxLayout, QListWidget, 
                             QListWidgetItem, QSplitter)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QFont, QCursor


try:
    import pyzipper
    HAS_PYZIPPER = True
except ImportError:
    HAS_PYZIPPER = False

try:
    from core.ZipCrackEngine import run_attack_engine
except ImportError:
    pass

class CrackerWorker(QThread):
    log_signal = pyqtSignal(str)           
    success_signal = pyqtSignal(str, list) 
    fail_signal = pyqtSignal()             
    error_signal = pyqtSignal(str)         

    def __init__(self, zip_path, dict_path=None):
        super().__init__()
        self.zip_path = zip_path
        self.dict_path = dict_path

    def run(self):
        try:
            def log_callback(msg):
                self.log_signal.emit(msg)

            password, contents = run_attack_engine(self.zip_path, self.dict_path, log_callback)

            if password:
                self.success_signal.emit(password, contents)
            else:
                self.fail_signal.emit()

        except Exception as e:
            self.error_signal.emit(str(e))



# giao diện chính
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Super Vip Pro Zip Cracker")
        self.setGeometry(100, 100, 800, 650)
        self.setAcceptDrops(True)

        self.zip_path = None
        self.dict_path = None
        self.found_password = None # lưu mật khẩu sau khi tìm thấy

        self.init_ui()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # khu vực chọn file 
        header_layout = QHBoxLayout()
        
        # vùng kéo thả nhỏ gọn bên trái
        self.lbl_drop = QLabel("KÉO FILE ZIP\nVÀO ĐÂY")
        self.lbl_drop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_drop.setFixedSize(120, 100)
        self.lbl_drop.setStyleSheet("border: 2px dashed #999; border-radius: 8px; background: #eee; color: #555;")
        header_layout.addWidget(self.lbl_drop)

        # các nút điều khiển bên phải
        ctl_layout = QVBoxLayout()
        
        btn_row1 = QHBoxLayout()
        self.btn_zip = QPushButton("📁 Chọn File ZIP")
        self.btn_zip.clicked.connect(self.browse_zip)
        btn_row1.addWidget(self.btn_zip)
        
        self.btn_dict = QPushButton("📖 Chọn Từ Điển")
        self.btn_dict.clicked.connect(self.browse_dict)
        btn_row1.addWidget(self.btn_dict)
        ctl_layout.addLayout(btn_row1)

        self.lbl_info = QLabel("Chưa chọn file...")
        self.lbl_info.setStyleSheet("color: #666; font-style: italic;")
        ctl_layout.addWidget(self.lbl_info)

        self.btn_start = QPushButton("BẮT ĐẦU BẺ KHÓA")
        self.btn_start.setFixedHeight(35)
        self.btn_start.setStyleSheet("background-color: #0078D7; color: white; font-weight: bold;")
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self.start_cracking)
        ctl_layout.addWidget(self.btn_start)

        header_layout.addLayout(ctl_layout)
        main_layout.addLayout(header_layout)


        # khu vực chia đôi: Log Terminal và danh sách kết quả
        splitter = QSplitter(Qt.Orientation.Vertical)



        # phần log
        group_log = QGroupBox("Nhật ký (Log Terminal)")
        vbox_log = QVBoxLayout()
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Consolas; font-size: 11px;")
        vbox_log.addWidget(self.txt_log)
        group_log.setLayout(vbox_log)
        splitter.addWidget(group_log)

        # danh sách file tìm thấy
        group_res = QGroupBox("Nội dung File ZIP (Double Click để mở file)")
        group_res.setStyleSheet("QGroupBox { font-weight: bold; color: blue; }")
        vbox_res = QVBoxLayout()
        
        self.list_files = QListWidget()
        self.list_files.setStyleSheet("font-size: 13px; padding: 5px;")
        self.list_files.setAlternatingRowColors(True)
        # kết nối sự kiện click đúp
        self.list_files.itemDoubleClicked.connect(self.open_extracted_file)
        
        vbox_res.addWidget(self.list_files)
        
        self.lbl_hint = QLabel("💡 Mẹo: Click đúp vào file trong danh sách trên để xem nội dung ngay lập tức.")
        self.lbl_hint.setStyleSheet("color: #555; font-size: 11px;")
        self.lbl_hint.setVisible(False)
        vbox_res.addWidget(self.lbl_hint)

        group_res.setLayout(vbox_res)
        splitter.addWidget(group_res)

        main_layout.addWidget(splitter)
        splitter.setSizes([150, 300])

    # mở file kết quả
    def open_extracted_file(self, item: QListWidgetItem):
        file_name = item.text()
        
        # bỏ qua nếu click vào thư mục (kết thúc bằng /)
        if file_name.endswith("/") or file_name.endswith("\\"):
            return

        if not self.found_password:
            QMessageBox.warning(self, "Lỗi", "Chưa có mật khẩu để giải nén.")
            return

        try:
            # hiện đồng hồ cát
            QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
            
            temp_dir = os.path.join(tempfile.gettempdir(), "ZipCracker_Temp")
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)

            extracted_path = self.extract_single_file(file_name, temp_dir, self.found_password)
            
            # mở file bằng ứng dụng mặc định của Windows
            if extracted_path and os.path.exists(extracted_path):
                if os.name == 'nt': # Windows
                    os.startfile(extracted_path)
                else: # Mac/Linux
                    subprocess.call(('xdg-open', extracted_path))
            
        except Exception as e:
            QMessageBox.critical(self, "Lỗi mở file", f"Không thể mở file này:\n{str(e)}")
        finally:
            QApplication.restoreOverrideCursor()

    def extract_single_file(self, filename, output_dir, password):
        pwd_bytes = password.encode('utf-8')
        
        # hàm nội bộ để giải nén
        def _extract(zf_instance):
            # extract cho phép giải nén 1 file cụ thể
            return zf_instance.extract(filename, path=output_dir, pwd=pwd_bytes)

        try:
            # ưu tiên dùng pyzipper nếu có (để hỗ trợ AES)
            if HAS_PYZIPPER:
                try:
                    with pyzipper.AESZipFile(self.zip_path) as zf:
                        return _extract(zf)
                except:
                    # fallback về zipfile thường nếu lỗi hoặc không phải AES
                    with zipfile.ZipFile(self.zip_path) as zf:
                        return _extract(zf)
            else:
                with zipfile.ZipFile(self.zip_path) as zf:
                    return _extract(zf)
        except Exception as e:
            raise e

    # UI
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls(): event.accept()
        self.lbl_drop.setStyleSheet("border: 2px dashed #0078D7; background: #e3f2fd;")

    def dragLeaveEvent(self, event):
        self.lbl_drop.setStyleSheet("border: 2px dashed #999; background: #eee;")

    def dropEvent(self, event: QDropEvent):
        self.lbl_drop.setStyleSheet("border: 2px dashed #999; background: #eee;")
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if files and files[0].lower().endswith('.zip'):
            self.load_zip(files[0])

    def browse_zip(self):
        f, _ = QFileDialog.getOpenFileName(self, "Chọn ZIP", "", "ZIP Files (*.zip)")
        if f: self.load_zip(f)

    def browse_dict(self):
        f, _ = QFileDialog.getOpenFileName(self, "Chọn Từ Điển", "", "Text (*.txt);;All (*)")
        if f:
            self.dict_path = f
            self.update_info()

    def load_zip(self, path):
        self.zip_path = path
        self.btn_start.setEnabled(True)
        self.lbl_drop.setText("ĐÃ NHẬN\nFILE ZIP")
        self.lbl_drop.setStyleSheet("border: 2px solid green; background: #e8f5e9; color: green; font-weight: bold;")
        self.list_files.clear() # xóa danh sách cũ
        self.update_info()

    def update_info(self):
        name = os.path.basename(self.zip_path)
        mode = "Dictionary" if self.dict_path else "Brute-Force (1-6 chars)"
        self.lbl_info.setText(f"File: {name}\nChế độ: {mode}")

    def start_cracking(self):
        self.btn_start.setEnabled(False)
        self.btn_zip.setEnabled(False)
        self.btn_dict.setEnabled(False)
        self.list_files.clear()
        self.txt_log.clear()
        self.found_password = None # reset mật khẩu cũ
        self.lbl_hint.setVisible(False)
        
        self.worker = CrackerWorker(self.zip_path, self.dict_path)
        self.worker.log_signal.connect(self.update_log)
        self.worker.success_signal.connect(self.on_success)
        self.worker.fail_signal.connect(self.on_fail)
        self.worker.error_signal.connect(self.on_error)
        self.worker.start()

    def update_log(self, msg):
        # tối ưu hiển thị log để không giật lag
        if msg.startswith("[-] Progress:"):
            cursor = self.txt_log.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            cursor.select(cursor.SelectionType.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.insertText(msg)
        else:
            self.txt_log.append(msg)
            sb = self.txt_log.verticalScrollBar()
            sb.setValue(sb.maximum())

    def on_success(self, password, contents):
        self.reset_ui()
        self.found_password = password # lưu mật khẩu lại
        
        self.txt_log.append("\n" + "="*30)
        self.txt_log.append(f"✅ THÀNH CÔNG! PASS: {password}")
        self.txt_log.append("="*30)

        # CẬP NHẬT DANH SÁCH FILE VÀO LIST WIDGET
        for file_name in contents:
            item = QListWidgetItem(file_name)
            # thêm icon 
            if file_name.endswith('/'):
                item.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_DirIcon))
            else:
                item.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_FileIcon))
            self.list_files.addItem(item)
        
        self.lbl_hint.setVisible(True)
        QMessageBox.information(self, "Bẻ khóa thành công", f"Mật khẩu là: {password}\n\nBạn có thể click đúp vào danh sách file bên dưới để mở!")

    def on_fail(self):
        self.reset_ui()
        QMessageBox.warning(self, "Thất bại", "Không tìm thấy mật khẩu.")

    def on_error(self, err):
        self.reset_ui()
        QMessageBox.critical(self, "Lỗi", err)

    def reset_ui(self):
        self.btn_start.setEnabled(True)
        self.btn_zip.setEnabled(True)
        self.btn_dict.setEnabled(True)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())