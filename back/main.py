# main.py の修正点

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse  # <-- ★この行を追加！
from camera_service import get_video_stream_generator, release_camera
# control_serviceをインポート
from control_service import init_gpio, update_motors, cleanup_gpio

# 1. FastAPIアプリケーションのインスタンスを作成（ASGIアプリケーション本体）
app = FastAPI()

# --- 起動・シャットダウンイベント ---
@app.on_event("startup")
def startup_event():
    """アプリケーション起動時にGPIOを初期化"""
    init_gpio()

@app.on_event("shutdown")
def shutdown_event():
    """アプリケーション終了時にカメラとGPIOを解放"""
    release_camera()
    cleanup_gpio()

# --- WebSocketsエンドポイント ---
@app.websocket("/ws/control")
async def control_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "control":
                # コントローラー入力を取得
                left_x = float(data.get("left_x", 0.0))
                throttle = float(data.get("left_y", 0.0))
                
                # ★ここで入力値を確認 (デバッグ用)
                print(f"Input: X={left_x:.2f}, Y={throttle:.2f}")
                print(f"data：{data}")

                # モーター制御サービスを呼び出し
                update_motors(left_x, throttle)
                
            elif data.get("type") == "ai_result":
                # AIの判断結果を処理（人検出など）
                # (ここに自律制御ロジックを組み込む)
                pass

    except WebSocketDisconnect:
        print("クライアント接続が切断されました。")
    finally:
        # 切断時にもモーターを停止
        update_motors(0.0, 0.0)

# ----------------------------------------------------
# 2. 映像配信の受け口（Controllerの役割）
# ----------------------------------------------------
@app.get("/video_feed")
def video_feed():
    # サービス層からジェネレータを取得し、レスポンスを返す
    return StreamingResponse(
        get_video_stream_generator(),  # サービス層の関数を呼び出し
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

# ... uvicorn main:app --workers 1 で起動