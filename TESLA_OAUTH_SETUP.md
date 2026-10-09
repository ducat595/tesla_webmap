# v7 Tesla OAuth 設定手順

## Tesla開発者ページ

OAuth付与タイプは「認証コードおよびM2M」。

| 項目 | 値 |
| --- | --- |
| 許可された送信元URL | https://ducat595.github.io |
| 許可されたリダイレクトURI | https://tesla-webmap.onrender.com/auth/tesla/callback |
| 許可されたリターンURL | 任意なので空欄 |

車両コマンド vehicle_cmds を許可する。認証では openid と offline_access も要求する。車両位置情報の権限は要求しない。

## Render環境変数

| キー | 値 |
| --- | --- |
| TESLA_CLIENT_ID | Teslaで発行されたClient ID |
| TESLA_CLIENT_SECRET | Teslaで発行されたClient Secret |
| TESLA_REDIRECT_URI | https://tesla-webmap.onrender.com/auth/tesla/callback |
| TESLA_OWNER_SECRET | 既存の32文字以上の所有者キー |
| ALLOWED_ORIGINS | https://ducat595.github.io |

Client SecretをGitHub、画面、チャットに貼らない。Renderの環境変数だけに保存する。変更後は再デプロイする。
Build Command: python -m compileall backend
Start Command: python backend/server.py
Health Check Path: /health

## 更新と操作

1. ZIP内のfrontend、backend、testsと文書をGitHubの同名パスへ上書きする。
2. Renderで最新コミットをデプロイする。
3. iPhoneの画面でv7表示を確認し、初回の所有者端末登録を行う。
4. 「iPhoneでTeslaにログイン」を押す。共有中は先に共有を停止する。
5. Tesla公式サイトで車両コマンドを許可する。
6. 完了画面の「アプリへ戻る」を押し、位置共有を再開し車載ブラウザを接続する。

コールバックURLを直接開くだけの場合は「認証が期限切れか…」と表示される。これは正常で、アプリから開始する必要がある。404ならbackendが更新されていないか公開URLが違う。

## v7仕様と制限

POST /auth/tesla/start は30日有効の所有者端末トークンを検証し、一度だけ使える開始リンクを返す。GET /auth/tesla/launch は10分有効のstateと開始リンクを検証して、Secure HttpOnly SameSite=Lax Cookieを設定しTeslaへ移動する。GET /auth/tesla/callback は同一ブラウザCookie、state、期限、所有者登録を検証し、認証コードを公式token APIへ送る。認証要求は一回で消費する。通信失敗は自動再試行しない。認証コード・トークン・秘密情報はログや完了HTMLに出さない。

取得したアクセストークンとリフレッシュトークンはサーバーのメモリだけに保存する。リフレッシュトークンの自動更新・永続保存は本版の対象外。再起動または期限切れで再ログインが必要。所有者キー変更で取得済みトークンも使用停止する。単一インスタンスで使用する。

Tesla送信はOAuthで取得した有効トークンを優先し、未取得・期限切れ時は既存のTESLA_ACCESS_TOKEN環境変数にフォールバックする。この変数を未設定にすればOAuthのみを使用する。

OAuthログイン成功だけでは実車送信は完成しない。署名プロキシ、車両への仮想キー登録、Fleet APIパートナー登録・公開鍵配置、TESLA_VINが別途必要。既存の経由地対応プロキシ制限はv6と同じ。Google Place IDも必要。

地域audienceは日本向けにNAの https://fleet-api.prd.na.vn.cloud.tesla.com を使う。

認証モジュールの本人確認・state・ブラウザ結び付け・期限・再利用拒否・キャンセル等を自動テストする。実際のTeslaログインと実車送信は資格情報未設定のため未確認。

公式仕様 https://developer.tesla.com/docs/fleet-api/authentication/third-party-tokens
