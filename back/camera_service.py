# FastAPIのRouterではなく、単なる関数を定義
import cv2 
import time

# カメラオブジェクトをグローバルで保持し、一度だけ初期化する
# Windows PCのWebカメラは通常インデックス 0
# ⚠ 注意: 実際のラズパイでは異なる初期化が必要です
camera = cv2.VideoCapture(0)

# 解像度設定（高速化のため低解像度に設定）
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
camera.set(cv2.CAP_PROP_FPS, 30)

def get_video_stream_generator():
    """FastAPIのStreamingResponseで使用するMJPEGフレームジェネレータ"""
    if not camera.isOpened():
        print("Error: Windows Webカメラにアクセスできません。")
        return
        
    print("カメラストリーミング開始...")
    
    while True:
        # 1. フレームの取得
        success, frame = camera.read()
        
        if not success:
            # カメラが切断されたり、フレームを読み込めなかった場合
            print("Warning: フレームの読み取りに失敗しました。")
            time.sleep(0.1)
            continue
        
        # 2. JPEGにエンコード
        # MJPEGストリーミングの標準形式
        # 画質を50%に落としてデータ量を削減（ラグ対策）
        (flag, encoded_image) = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
        
        if not flag:
            continue
            
        # 3. MJPEG形式のHTTPストリームデータとしてyield
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + bytearray(encoded_image) + b'\r\n')
        
        # 4. フレームレート制御 (CPU負荷軽減のため少し待機)
        time.sleep(0.01) 

# アプリケーション終了時にカメラリソースを解放するための処理（オプションだが推奨）
# Uvicornのシャットダウンフックなどで呼び出すと良い
def release_camera():
    if camera.isOpened():
        camera.release()
        print("カメラリソースを解放しました。")