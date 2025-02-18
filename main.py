from pirc522 import RFID
import RPi.GPIO as GPIO
import time
import pygame
from firebase_admin import credentials, firestore, initialize_app

# Firebase設定
FIREBASE_CRED = "hengen-zizai-firebase-adminsdk-fbsvc-e5b7d0df74.json"
BAND_UUID = "aaa"

# Firebase認証
cred = credentials.Certificate(FIREBASE_CRED)
initialize_app(cred)
db = firestore.client()

# 画面セットアップ (pygame)
pygame.init()
screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)  # フルスクリーン設定に変更
pygame.mouse.set_visible(False)  # マウスカーソルを非表示
pygame.display.set_caption("NFC Scanner")

# 日本語フォントの設定（例: TakaoPGothicフォントを使用）
try:
    font_path = "./fonts/GenJyuuGothic-Bold.ttf"  # 一般的なRaspberry Piの日本語フォントパス
    font = pygame.font.Font(font_path, 50)  # 文字サイズを大きく調整
except:
    font = pygame.font.SysFont(["Inter", "noto sans cjk jp"], 50)  # 代替フォント指定

# 音声セットアップ
pygame.mixer.init()
# scan_sound = pygame.mixer.Sound("scan.wav")

# チェックポイント番号
MACHINE_NUM=1

# チェックポイントの数
CHECKPOINT_NUM=5


def parse_ndef(data):
    global BAND_UUID
    index = 0
    flg = 0
    while index < len(data):
        if data[index] == 0x03:  # NDEF開始 (0x03: NDEF Message TLV)
            ndef_length = data[index + 1]  # NDEF全体の長さ
            index += 2  # 0x03 と長さの部分をスキップ

            while index < ndef_length + 2:
                tnf = data[index] & 0x7  # TNF（Type Name Format）
                type_length = data[index + 1]  # Typeの長さ
                payload_length = data[index + 2]  # ペイロードの長さ
                record_type = data[index + 3]  # Record Type

                if record_type == 0x54:  # 'T' (Text Record)
                    lang_length = data[index + 4] & 0x3F  # 言語コードの長さ
                    lang_code = data[index + 5 : index + 5 + lang_length].decode("utf-8")
                    text_data = data[index + 5 + lang_length : index + 4 + payload_length].decode("utf-8")
                    
                    print("言語コード:", lang_code)
                    print("テキストデータ:", text_data)
                    print("----------------------")

                    BAND_UUID = text_data
                    flg = 1

                index += 3 + type_length + payload_length
        index += 1
    print("NDEF解析終了")
    if flg == 1:
      return True
    else:
      return False

rdr = RFID()

# UI描画関数
def display_text(text, color=(245,245,220), background=(25, 25, 112), 
                outline_color=(0,0,0)):
    screen.fill(background)
    
    # テキストのアウトライン描画（影効果）
    outline_surface = font.render(text, True, outline_color)
    outline_pos = (screen.get_width()//2 - outline_surface.get_width()//2 + 3, 
                  screen.get_height()//2 - outline_surface.get_height()//2 + 3)
    screen.blit(outline_surface, outline_pos)
    
    # メインテキスト描画
    text_surface = font.render(text, True, color)
    text_rect = text_surface.get_rect(center=(screen.get_width()//2, screen.get_height()//2))
    
    screen.blit(text_surface, text_rect)
    pygame.display.update()

# NFC読み取りモード
def read_mode():
    display_text("NFCを近づけてね！", (245,245,220), (25, 25, 112))

# 読み取ったNFCタグのUIDをFirebaseに送信
def handle_nfc_scan():
    global BAND_UUID, MACHINE_NUM
    try:
        # print("データ読み取り中 ...")
        full_data = []
        rdr.wait_for_tag()
        (error, tag_type) = rdr.request()
        st = False
        if not error:
            (error, uid) = rdr.anticoll()
            if not error:
                print("UID:", uid)
                if not rdr.select_tag(uid):
                    for block in range(4, 25):
                        status, read_data = rdr.read(block)
                        if not status:
                            full_data.extend(read_data[:4])
                            if read_data[0] == 0xFE:
                                break
                    rdr.stop_crypto()
                    st = parse_ndef(bytearray(full_data))
        if st == True:
            print("BAND UUID: ", BAND_UUID)
            display_text("通信中....", (255,255,255), (34,139,34))

            # Firebaseからデータ取得
            band_ref = db.collection("bands").document(BAND_UUID)
            band_data = band_ref.get().to_dict()

            print(band_data)
            if band_data:
                sex = band_data.get("sex", "その他")
                age = band_data.get("age", 0)


                # スタンプラリーチェック
                checkpoint_status = []
                for i in range(5):  # 5つのチェックポイントを確認
                    code = ord('A')
                    check_path = f"checkpoints/1{chr(code+i)}/checked/{BAND_UUID}"
                    exists = db.document(check_path).get().exists
                    checkpoint_status.append(exists)

                checkpoint_status[MACHINE_NUM]=True

                # スタンプ表示
                screen.fill((120, 60, 250))
                text_surface = font.render("スタンプ状況", True, (245,245,220))
                text_rect = text_surface.get_rect(center=(screen.get_width()//2, screen.get_height()//4))
                screen.blit(text_surface, text_rect)

                # 上の端っこに情報表示
                text_surface = font.render(f"性別: {sex} 年齢: {age}", True, (245,245,220))
                text_rect = text_surface.get_rect(center=(screen.get_width()//2, screen.get_height()//10))
                screen.blit(text_surface, text_rect)

                circle_radius = 30
                spacing = screen.get_width() // (CHECKPOINT_NUM+1)
                start_time = time.time()
                lit = True  # 点滅状態フラグ
                
                # 3秒間アニメーションループ
                while time.time() - start_time < 3:
                    # 点滅状態を0.5秒ごとに切り替え
                    if int((time.time() - start_time) * 2) % 2 == 0:
                        lit = not lit
                    
                    # スタンプ再描画
                    for i, status in enumerate(checkpoint_status):
                        x = (i + 1) * spacing
                        y = screen.get_height() * 3 // 4
                        if status:
                            # 登録済み
                            # チェックポイント番号の場合アニメーション
                            if i == MACHINE_NUM:
                                pygame.draw.circle(screen, (62,255,171) if lit else (25, 80, 112), (x, y), circle_radius, 0)
                                if not lit :
                                    pygame.draw.circle(screen, (245,245,220), (x, y), circle_radius, 2)
                            else:
                                pygame.draw.circle(screen, (62,255,171), (x, y), circle_radius, 0)
                        else:
                            # 未登録
                            pygame.draw.circle(screen, (245,245,220), (x, y), circle_radius, 2)
                    
                    pygame.display.update()
                    pygame.time.wait(300)  # アニメーション速度調整
                    pygame.event.pump()  # イベントループを維持

                # チェックポイントの更新
                timestamp = int(time.time() * 1000)
                code = ord('A')
                checkpoint_path = f"checkpoints/1{chr(code+MACHINE_NUM)}/checked/{BAND_UUID}"
                db.document(checkpoint_path).set({"timestamp": str(timestamp)})
                
                display_text("スタンプ登録完了！", (255,255,255), (34,139,34))
                time.sleep(3)
            else:
                display_text("データがありません", (255,255,255), (178,34,34))
                time.sleep(3)
                

    except Exception as e:
        print(f"Error: {e}")
        display_text("エラー発生", (255,255,255), (178,34,34))
        time.sleep(2)

# メインループ
if __name__ == "__main__":
    read_mode()
    while True:
        try:
            pygame.event.get()
            handle_nfc_scan()
            read_mode()
        except KeyboardInterrupt:
            rdr.cleanup()
            GPIO.cleanup()
            print("Program terminated")
            break
