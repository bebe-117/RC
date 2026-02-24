<script setup>
import { ref, onMounted, onUnmounted } from 'vue';

// ----------------------------------------------------
// ⚠️ 重要: IPアドレスをRaspberry Pi Zero 2 WのIPに置き換えてください。
// ----------------------------------------------------
// const PI_IP = '192.168.x.x'; // 例: Pi Zero 2 WのIPアドレス
const PI_IP = window.location.hostname
; // ここをRaspberry Piの実際のIPに変更
const PORT = 8000;          // FastAPIサーバーのポート
const ENDPOINT = '/video_feed';

const videoFeedUrl = ref('');
const isCameraError = ref(false);
let lastSentTime = 0; // 前回の送信時刻を記録
const SEND_INTERVAL = 50; // 送信間隔（ミリ秒）。50ms = 毎秒20回

// キーボード入力の状態管理
const keyState = { w: false, a: false, s: false, d: false };
const onKeyDown = (e) => {
    if (keyState.hasOwnProperty(e.key.toLowerCase())) keyState[e.key.toLowerCase()] = true;
};
const onKeyUp = (e) => {
    if (keyState.hasOwnProperty(e.key.toLowerCase())) keyState[e.key.toLowerCase()] = false;
};

onMounted(() => {
  // コンポーネントがマウントされたら、映像のURLを設定
  videoFeedUrl.value = `http://${PI_IP}:${PORT}${ENDPOINT}`;
});

onMounted(() => {
    // コンポーネントが画面に表示されたらポーリング開始
    window.addEventListener("gamepadconnected", startGamepadPolling);
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    // 既に接続されている可能性もあるため、直接呼び出す
    connectWebSocket();
    startGamepadPolling(); 
});

onUnmounted(() => {
    // コンポーネントが画面から消えたらポーリングを停止
    if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
    }
    window.removeEventListener("gamepadconnected", startGamepadPolling);
    window.removeEventListener("keydown", onKeyDown);
    window.removeEventListener("keyup", onKeyUp);
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (ws) {
        ws.onclose = null; // 再接続ロジックを無効化
        ws.close();
    }
});

let animationFrameId = null;
let ws = null;
let reconnectTimer = null;

function connectWebSocket() {
    ws = new WebSocket(`ws://${PI_IP}:${PORT}/ws/control`);
    
    ws.onopen = () => {
        console.log("✅ WebSocket接続成功");
    };
    
    ws.onclose = () => {
        console.warn("⚠️ WebSocket切断: 3秒後に再接続します...");
        ws = null;
        reconnectTimer = setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = (err) => {
        console.error("❌ WebSocketエラー:", err);
        ws.close();
    };
}

function startGamepadPolling() {
    let logCounter = 0;
    
    function gameLoop() {
        const gamepads = navigator.getGamepads();
        const ps4Controller = gamepads[0]; // 最初の接続されたコントローラー (DS4)

        // --- 入力値の計算 (キーボード + コントローラー) ---
        let lx = 0;
        let ly = 0;
        let cross = false;
        let circle = false;

        // 1. キーボード入力
        if (keyState.w) ly -= 1.0;
        if (keyState.s) ly += 1.0;
        if (keyState.a) lx -= 1.0;
        if (keyState.d) lx += 1.0;

        // 2. コントローラー入力 (接続されていれば加算/上書き)
        if (ps4Controller) {
            lx += ps4Controller.axes[0];
            ly += ps4Controller.axes[1];
            // 値を -1.0 ~ 1.0 に制限
            lx = Math.max(-1.0, Math.min(1.0, lx));
            ly = Math.max(-1.0, Math.min(1.0, ly));
            
            cross = ps4Controller.buttons[0].pressed;
            circle = ps4Controller.buttons[1].pressed;
        }

        if (ws && ws.readyState === WebSocket.OPEN) {
            const currentTime = performance.now();
            if (currentTime - lastSentTime > SEND_INTERVAL) {
                // 取得したアナログ値をJSONオブジェクトにまとめて送信
                const controlData = {
                    type: 'control',
                    left_x: lx.toFixed(3),
                    left_y: ly.toFixed(3),
                    cross_b: cross,
                    circle_b: circle,
                };
    
                // WebSocketsでFastAPIに送信
                ws.send(JSON.stringify(controlData));
                lastSentTime = currentTime; // 送信時刻を更新
            }
        } else {
            // 送信できない理由をログに出力 (大量に出ないよう約1秒に1回表示)
            logCounter++;
            if (logCounter % 60 === 0) {
                if (!ws || ws.readyState !== WebSocket.OPEN) {
                    const state = ws ? ws.readyState : 'NULL';
                    console.warn(`⚠️ WebSocket未接続: サーバーに繋がっていません (State: ${state})`);
                }
            }
        }

        // 次の画面描画タイミングで関数を再度呼び出す (毎秒約60回)
        animationFrameId = requestAnimationFrame(gameLoop);
    }
    
    // 初回実行
    animationFrameId = requestAnimationFrame(gameLoop);
}

function handleCameraError() {
    // カメラ映像の読み込みに失敗した場合の処理
    // (コンソールにエラーが出るのを防ぐことはできませんが、UIを切り替えます)
    if (!isCameraError.value) {
        console.warn("カメラ映像が見つかりません。映像なしモードで動作します。");
        isCameraError.value = true;
    }
}

async function toggleFullscreen() {
    try {
        if (!document.fullscreenElement) {
            // 全画面表示を開始
            await document.documentElement.requestFullscreen();
            // スマホなどで横向きにロック (対応ブラウザのみ)
            if (screen.orientation && screen.orientation.lock) {
                await screen.orientation.lock('landscape').catch(e => console.warn('Orientation lock failed:', e));
            }
        } else {
            // 全画面表示を終了
            if (document.exitFullscreen) {
                await document.exitFullscreen();
                // 向きのロック解除
                if (screen.orientation && screen.orientation.unlock) {
                    screen.orientation.unlock();
                }
            }
        }
    } catch (err) {
        console.error("Fullscreen error:", err);
    }
}
</script>

<template>
  <div class="camera-view">
    <img 
        v-if="!isCameraError"
        :src="videoFeedUrl" 
        alt="ライブカメラ映像" 
        class="video-stream" 
        @error="handleCameraError"
    />
    <div v-else class="no-signal">
        <p>NO CAMERA SIGNAL</p>
        <p>操作は可能です</p>
    </div>

    <!-- 全画面切り替えボタン -->
    <button class="fullscreen-btn" @click="toggleFullscreen" title="全画面表示">
        <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" />
        </svg>
    </button>
  </div>
</template>

<style scoped>
.camera-view {
  position: fixed; /* 画面に固定 */
  top: 0;
  left: 0;
  width: 100vw;    /* 画面幅いっぱい */
  height: 100dvh;  /* 画面高さいっぱい (スマホのアドレスバー考慮) */
  background-color: #000; /* 余白は黒 */
  display: flex;
  justify-content: center;
  align-items: center;
  overflow: hidden;
}

.video-stream {
  width: 100%;
  height: 100%;
  object-fit: contain; /* 比率を維持して画面内に収める */
  /* もし画面いっぱいに引き伸ばして端が見切れても良いなら 'cover' に変更してください */
}
.no-signal {
  width: 100%;
  height: 100%;
  background-color: #1a1a1a;
  color: #ff5555;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  font-family: monospace;
  font-size: 1.2rem;
}

.fullscreen-btn {
  position: absolute;
  bottom: 20px;
  right: 20px;
  width: 48px;
  height: 48px;
  background-color: rgba(0, 0, 0, 0.5);
  border: 2px solid rgba(255, 255, 255, 0.7);
  border-radius: 8px;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 1000;
  transition: background-color 0.2s, transform 0.1s;
}

.fullscreen-btn:hover {
  background-color: rgba(0, 0, 0, 0.8);
}

.fullscreen-btn:active {
  transform: scale(0.95);
}
</style>
