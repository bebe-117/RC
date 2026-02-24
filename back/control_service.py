# control_service.py

import queue
import threading
import time

# --- Windows/非Pi環境のためのダミーGPIOクラス ---
try:
    # Raspberry Pi環境の場合
    import RPi.GPIO as GPIO
    GPIO_ENABLED = True
    print("RPi.GPIOをインポートしました。")
except ModuleNotFoundError:
    # Windowsなどの非Pi環境の場合
    class DummyGPIO:
        BCM = 11
        OUT = 1
        LOW = 0
        HIGH = 1
        def setmode(self, mode): pass
        def setup(self, pins, mode): pass
        def output(self, pins, state): pass
        def cleanup(self): pass
        def PWM(self, pin, freq):
            class DummyPWM:
                def start(self, dc): pass
                def ChangeDutyCycle(self, dc): pass
                def stop(self): pass
            return DummyPWM()

    GPIO = DummyGPIO()
    GPIO_ENABLED = False
    print("RPi.GPIOが見つかりませんでした。ダミーのGPIOを使用します。")

# --- 📌 GPIOピン設定 ---
# L298N モータードライバーのピン配置例 (BCM番号)
# Motor A: ステアリング用 (前モーター: 方向転換)
PIN_AIN1 = 17
PIN_AIN2 = 27
PIN_APWM = 22

# Motor B: 駆動用 (後ろモーター: 前後移動)
PIN_BIN1 = 23
PIN_BIN2 = 24
PIN_BPWM = 25

PWM_FREQ = 50  # PWM周波数 (Hz)
DEAD_ZONE = 0.05 # スティックの入力無視範囲 (0.0 ~ 1.0)

# PWMインスタンス保持用
pwm_a = None
pwm_b = None

# --- ワーカースレッド関連 ---
_motor_command_queue = None
_worker_thread = None

def init_gpio():
    """GPIOピンの初期設定とワーカースレッドの開始"""
    global pwm_a, pwm_b, _worker_thread, _motor_command_queue
    
    if not GPIO_ENABLED:
        print("GPIOは無効化されています。")
        return # Windowsではここで終了
    
    # GPIOモード設定
    GPIO.setmode(GPIO.BCM)
    
    # ピンを出力モードに設定
    pins = [PIN_AIN1, PIN_AIN2, PIN_APWM, PIN_BIN1, PIN_BIN2, PIN_BPWM]
    GPIO.setup(pins, GPIO.OUT)
    
    # PWMインスタンスの作成と開始
    pwm_a = GPIO.PWM(PIN_APWM, PWM_FREQ)
    pwm_b = GPIO.PWM(PIN_BPWM, PWM_FREQ)
    
    pwm_a.start(0)
    pwm_b.start(0)

    # コマンドキューとワーカースレッドの初期化と開始
    _motor_command_queue = queue.Queue(maxsize=1)
    if _worker_thread is None:
        _worker_thread = threading.Thread(target=_motor_worker, daemon=True)
        _worker_thread.start()

    print("GPIO Initialized.")
    
def cleanup_gpio():
    """アプリケーション終了時のリソース解放"""
    global pwm_a, pwm_b, _worker_thread
    if not GPIO_ENABLED:
        return
    
    # ワーカースレッドを停止
    if _worker_thread is not None:
        if _motor_command_queue: _motor_command_queue.put(None)  # 停止の合図
        _worker_thread.join(timeout=2) # 終了を待つ
        _worker_thread = None

    if pwm_a:
        pwm_a.stop()
    if pwm_b:
        pwm_b.stop()
        
    GPIO.cleanup()
    print("GPIO Cleaned up.")

def _motor_worker():
    """キューからモーター制御コマンドを取得して実行するワーカースレッド"""
    print("Motor worker thread started.")
    while True:
        try:
            # キューが空の場合、ここでブロックして待機
            command = _motor_command_queue.get()

            if command is None:
                # Noneを受け取ったらスレッドを終了
                print("Motor worker thread stopping.")
                break

            steering_speed, throttle_speed = command

            # モーター制御の実行
            _set_motor(pwm_a, PIN_AIN1, PIN_AIN2, steering_speed)  # ステアリング
            _set_motor(pwm_b, PIN_BIN1, PIN_BIN2, throttle_speed)  # 駆動
            print(f"🚀 Motor Output: Steer={steering_speed:.2f}, Drive={throttle_speed:.2f}")

        except Exception as e:
            print(f"Error in motor worker thread: {e}")

def _set_motor(pwm_obj, in1, in2, speed):
    """
    個別のモーターを制御するヘルパー関数
    speed: -1.0 (後退) ~ 1.0 (前進)
    """
    if pwm_obj is None: return

    # デューティ比 (0-100)
    duty = abs(speed) * 100
    if duty > 100: duty = 100
    
    # 方向制御
    if speed > 0: # 前進
        GPIO.output(in1, GPIO.HIGH)
        GPIO.output(in2, GPIO.LOW)
    elif speed < 0: # 後退
        GPIO.output(in1, GPIO.LOW)
        GPIO.output(in2, GPIO.HIGH)
    else: # 停止
        GPIO.output(in1, GPIO.LOW)
        GPIO.output(in2, GPIO.LOW)
        
    pwm_obj.ChangeDutyCycle(duty)

def update_motors(left_x: float, throttle: float):
    """コントローラーの入力値をキューに送信する"""
    if not GPIO_ENABLED:
        # Windowsの場合、制御は行わず、デバッグ情報を表示
        print(f"⚠️ DEBUG (No GPIO): LeftX={left_x:.2f}, Throttle={throttle:.2f}")
        return
    # コントローラー入力: throttleは通常 上が-1、下が1
    # 前進を正の値にするため反転
    drive = -throttle
    turn = left_x
    
    # デッドゾーン処理: 小さな入力ノイズを無視してモーターの微振動を防ぐ
    if abs(drive) < DEAD_ZONE: drive = 0.0
    if abs(turn) < DEAD_ZONE: turn = 0.0
    
    # --- ラジコン方式 (ステアリング + 駆動) ---
    # Motor A (前) = ステアリング (turn)
    # Motor B (後) = 駆動 (drive)
    # 📝 NOTE: 実際の配線がコメントと逆（モーターAが駆動、モーターBがステアリング）になっているため、
    # ソフトウェア側でロジックを入れ替えて対応します。
    # 本来: steering_speed = turn, throttle_speed = drive
    steering_speed = drive
    throttle_speed = turn
    
    # 値を -1.0 ~ 1.0 に制限
    steering_speed = max(min(steering_speed, 1.0), -1.0)
    throttle_speed = max(min(throttle_speed, 1.0), -1.0)
    
    # ワーカースレッドにコマンドを送信
    if _motor_command_queue is not None:
        try:
            # 既存の古いコマンドを破棄し、最新のコマンドをキューに入れる
            _motor_command_queue.get_nowait()
        except queue.Empty:
            pass # キューが空の場合は何もしない
        try:
            _motor_command_queue.put_nowait((steering_speed, throttle_speed))
        except queue.Full:
            pass # 非常に稀なレースコンディション。コマンドを破棄する。