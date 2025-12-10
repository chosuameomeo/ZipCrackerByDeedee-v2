# core/ZipTest.py

import os
import sys
import time
import zipfile
import string
import itertools
import multiprocessing
import signal
import shutil
import threading
from datetime import timedelta

try:
    import pyzipper
    HAS_PYZIPPER = True
except ImportError:
    pyzipper = None
    HAS_PYZIPPER = False


CHARSET_DIGITS = string.digits
CHARSET_LOWER = string.ascii_lowercase
CHARSET_UPPER = string.ascii_uppercase
CHARSET_SYMBOLS = string.punctuation
CHARSET_FULL = CHARSET_LOWER + CHARSET_UPPER + CHARSET_DIGITS + CHARSET_SYMBOLS

BATCH_SIZE = 5000 

# biến trạng thái hiển thị
monitor_status = {
    "stop": False,
    "total": 0,
    "checked": 0,
    "start_time": 0,
    "current_pwd": "Init...",
    "found": None,
    "lock": threading.Lock()
}

# biến toàn cục cho worker process
worker_zf = None
worker_target_file = None
worker_is_aes = False



def is_zip_encrypted(file_path):
    try:
        with zipfile.ZipFile(file_path) as zf:
            for info in zf.infolist():
                if info.flag_bits & 0x1: return True
    except: return False
    return False

def get_smallest_file(zip_path):
    best_file = None
    min_size = float('inf')
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for info in zf.infolist():
                if not info.is_dir() and not info.filename.endswith('/'):
                    if info.file_size < min_size:
                        min_size = info.file_size
                        best_file = info.filename
        if best_file is None:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                name_list = zf.namelist()
                if name_list: best_file = name_list[0]
    except Exception: return None
    return best_file

def count_lines_fast(filepath):
    def _make_gen(reader):
        b = reader(1024 * 1024)
        while b:
            yield b
            b = reader(1024 * 1024)
    with open(filepath, 'rb') as f:
        c_gen = _make_gen(f.raw.read)
        return sum(buf.count(b'\n') for buf in c_gen)

def init_worker(zip_path, target_file, use_aes):
    global worker_zf, worker_target_file, worker_is_aes
    worker_target_file = target_file
    worker_is_aes = use_aes
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        if use_aes and HAS_PYZIPPER:
            worker_zf = pyzipper.AESZipFile(zip_path, 'r')
        else:
            worker_zf = zipfile.ZipFile(zip_path, 'r')
    except: worker_zf = None

def crack_batch(passwords):
    global worker_zf, worker_target_file
    if worker_zf is None: return None, passwords[-1]

    for pwd in passwords:
        try:
            worker_zf.setpassword(pwd.encode('utf-8'))
            worker_zf.read(worker_target_file)
            return pwd, pwd
        except (RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile):
            continue
        except Exception:
            continue
    return None, passwords[-1]


def display_progress(callback_func):
    """Luồng hiển thị gửi dữ liệu về GUI thông qua callback"""
    while not monitor_status["stop"]:
        time.sleep(0.15) 
        with monitor_status["lock"]:
            checked = monitor_status["checked"]
            total = monitor_status["total"]
            start_t = monitor_status["start_time"]
            current = monitor_status["current_pwd"]
            
            elapsed = time.time() - start_t
            speed = checked / elapsed if elapsed > 0 else 0
            
            if total > 0:
                percent = (checked / total) * 100
                remaining = (total - checked) / speed if speed > 0 else 0
                eta_str = str(timedelta(seconds=int(remaining)))
            else:
                percent = 0.0
                eta_str = "Calculating..."

            speed_str = f"{int(speed):,}"
            display_pwd = (current[:15] + '..') if len(current) > 15 else current

            # tạo chuỗi log
            msg = (f"[-] Progress: {percent:5.2f}% | "
                   f"Speed: {speed_str} p/s | "
                   f"ETA: {eta_str} | "
                   f"Trying: {display_pwd}")
            
            # gửi về GUI nếu có callback
            if callback_func:
                callback_func(msg)
            else:
                # fallback in ra console nếu chạy terminal
                sys.stdout.write(f"\r{msg}")
                sys.stdout.flush()

def dict_generator(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        batch = []
        for line in f:
            line = line.strip('\r\n')
            if line:
                batch.append(line)
                if len(batch) >= BATCH_SIZE:
                    yield batch
                    batch = []
        if batch: yield batch

def bruteforce_generator(charset, min_len, max_len):
    for length in range(min_len, max_len + 1):
        total_for_len = len(charset) ** length
        with monitor_status["lock"]:
             monitor_status["total"] += total_for_len
        
        batch = []
        for p in itertools.product(charset, repeat=length):
            batch.append(''.join(p))
            if len(batch) >= BATCH_SIZE:
                yield batch
                batch = []
        if batch: yield batch

def run_attack_engine(zip_path, dict_path=None, callback_msg=None):
    """
    Hàm chính để gọi từ GUI.
    callback_msg: Hàm nhận chuỗi thông báo (log)
    """
    
    # hàm log cục bộ
    def log(text):
        if callback_msg: callback_msg(text)
        else: print(text)

    target_file = get_smallest_file(zip_path)
    if not target_file:
        log("[!] Error: File ZIP trống hoặc bị lỗi cấu trúc.")
        raise Exception("Invalid ZIP File")

    # check AES
    use_aes = False
    if HAS_PYZIPPER:
        try:
            with pyzipper.AESZipFile(zip_path) as zf: pass
            use_aes = True
        except: pass
    if not use_aes and is_zip_encrypted(zip_path) and HAS_PYZIPPER: use_aes = True

    # Setup Status
    monitor_status["total"] = 0
    monitor_status["checked"] = 0
    monitor_status["start_time"] = time.time()
    monitor_status["stop"] = False
    monitor_status["found"] = None

    # Chọn Generator
    generator = None
    
    if dict_path and os.path.exists(dict_path):
        log(f"[*] Đang sử dụng chế độ Từ Điển: {os.path.basename(dict_path)}")
        log("[*] Đang đếm số dòng (vui lòng chờ)...")
        total_lines = count_lines_fast(dict_path)
        monitor_status["total"] = total_lines
        generator = dict_generator(dict_path)
    else:
        log("[*] Không có từ điển -> Chuyển sang chế độ Brute-Force (1-6 ký tự).")
        monitor_status["total"] = 0 # sẽ tự tăng
        generator = bruteforce_generator(CHARSET_FULL, 1, 6)

    
    t = threading.Thread(target=display_progress, args=(callback_msg,))
    t.daemon = True
    t.start()

    cpu_count = multiprocessing.cpu_count()
    log(f"[+] Bắt đầu tấn công trên {cpu_count} luồng CPU...")

    
    pool = multiprocessing.Pool(processes=cpu_count, initializer=init_worker, initargs=(zip_path, target_file, use_aes))

    try:
        for found_pwd, last_tried in pool.imap_unordered(crack_batch, generator):
            with monitor_status["lock"]:
                monitor_status["checked"] += BATCH_SIZE
                monitor_status["current_pwd"] = last_tried
            
            if found_pwd:
                monitor_status["found"] = found_pwd
                monitor_status["stop"] = True
                pool.terminate()
                break
    except Exception as e:
        monitor_status["stop"] = True
        pool.terminate()
        log(f"[!] Lỗi Process: {e}")
    finally:
        monitor_status["stop"] = True
        pool.join()
        t.join()

    # trả về kết quả
    if monitor_status["found"]:
        pwd = monitor_status["found"]
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                contents = zf.namelist()
        except: contents = ["(Không thể đọc danh sách file)"]
        return pwd, contents
    else:
        return None, None