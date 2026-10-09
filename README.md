# Tesla Location Link v1 — iPhone → Model 3 現在地共有

2026年式Model 3の車載ブラウザで、iPhoneから受け取った現在地を表示する試験版。
Bluetoothは使いません。Googleマップアプリのミラーリングではありません。
ルート検索、リルート、音声案内、Tesla車両APIとの連携は含みません。

## 1. GitHub Pages

1. 新しいGitHubリポジトリを作ります（既存の株アプリとは別にしてください）。
2. このZIPの中身をアップロードします。
3. リポジトリの Settings → Pages → Deploy from a branch → main / root を選択します。
4. 使用する画面のURLは `https://ユーザー名.github.io/リポジトリ名/frontend/` です。

## 2. Render（新規サービス）

既存のEDINET/株アプリ用サービスは変更しません。

1. Renderで New → Web Service → 上記GitHubリポジトリを接続。
2. Language: Python 3、Root Directory: 空欄。
3. Build Command: `python -m compileall backend`
4. Start Command: `python backend/server.py`
5. 環境変数 `ALLOWED_ORIGINS` に `https://ユーザー名.github.io` を設定。
   リポジトリ名や `/frontend/` は含めません。末尾の `/` も不要です。
6. `/health` をヘルスチェックに指定し、デプロイ。
7. Renderの公開URLを控えます。例：`https://tesla-location-relay.onrender.com`。

`render.yaml` を使うBlueprint方式でも作成できます。プランの料金は契約画面で確認してください。
単一プロセス・単一インスタンスで動作します。セッションはメモリ保持で、再起動・再デプロイで消えます。
アイドル休止からの初回起動は時間がかかる場合があります。通信タイムアウト時は再試行してください。

## 3. iPhone側

1. SafariでPagesの画面を開く。
2. 「iPhone：現在地を送る」を選ぶ。
3. Renderの公開URLを入力して「設定を保存」。
4. 「共有を開始」を押し、位置情報を許可。
5. 表示された16桁の接続コードを車側で入力します。
6. Safariのページを表示したままにします。画面ロック・他アプリへの切替で更新が止まる場合があります。

画面の自動ロック設定を変更する場合は試験後に戻してください。バックグラウンド位置共有は保証しません。
位置更新が来たときに最短2秒間隔で送信します。常に2秒ごとにGPS更新されるわけではありません。

## 4. テスラ側（初回確認は停車中）

1. 車載ブラウザで同じPages URLを開く。
2. 「テスラ：地図を見る」を選ぶ。
3. 同じRender URLを入力して保存。
4. iPhoneの接続コードを入力して「接続」。3秒ごとに確認します。
5. 位置マーカー、精度の円、受信時刻、座標が表示されることを確認。
6. 15秒以上古い位置には更新停止メッセージを表示します。
7. 地図をドラッグすると追従を止めます。「現在地を中心に」で再開。

車載ブラウザ自体のGPSは使いません。インターネット接続が双方に必要です。
iPhoneのインターネット共有（Wi-Fi）で車を接続することもできますが、位置データはサーバー経由です。
実車のブラウザ互換性、走行中の表示可否、外部地図読み込みは未確認です。

## 地図の選択

初期状態はOpenStreetMap + Leafletです。Google APIキーなしで位置共有を試せます。
Google地図を使う場合：Google CloudでMaps JavaScript APIを有効化し、課金アカウントを設定。
APIキーのウェブサイト制限をPages URLに、API制限をMaps JavaScript APIだけに設定します。
「Googleマップを使う設定」にキーを入力して保存し、ページを再読み込み。
キーはブラウザで使用する公開用キーです。無制限のキーやサーバー用秘密キーを入れないでください。
APIキーは端末のlocalStorageに保存されます。外部ライブラリとタイルはインターネットから読み込みます。
Google Maps JavaScript API: https://developers.google.com/maps/documentation/javascript/get-api-key
OpenStreetMapタイルは少人数の動作確認用です。商用・多数ユーザー向け運用には適切なタイル提供元を選んでください。

## 停止・情報の扱い

iPhoneの「共有を停止・削除」で送信を止め、サーバー上のセッションと座標を削除。
通信失敗時は位置送信だけ停止し、削除ボタンで再試行できます。
タブを閉じるだけではサーバーの情報は直ちに消えません。作成から1時間で失効します。
期限後のメモリ削除は次のAPIアクセス時に行います。履歴やデータベースは保存しません。
接続コードは閲覧権限そのものです。他人に共有しないでください。URLやログには入れません。
書き込み・削除には別のランダムな送信トークンを使います。トークンはlocalStorageには保存しません。
ブラウザ設定の中継URL・地図キー・役割のみ端末に保存します。
接続コードなしで座標を一覧取得するAPIはありません。

## ローカル検証

`python -m unittest discover -s tests -v`

フロント：`python -m http.server 8080` をfrontend内で実行。
バックエンド：`ALLOWED_ORIGINS=http://localhost:8080 python backend/server.py`
画面のAPI URLには `http://localhost:8000` を設定。
iPhoneの位置情報試験はHTTPS公開URLで行ってください。

## 検証範囲

同梱テストは中継APIの実HTTP通信を検証します。実iPhone、実Tesla、Render本番、Google地図の実キーでの接続は未実施。
