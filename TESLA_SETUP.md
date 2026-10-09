# Tesla標準ナビへの実送信の準備

## 現在の完成範囲

Webの経由地編集・順序共有・ルート表示と、署名プロキシへの送信処理を実装しました。
Teslaアカウントの登録・認証、仮想キー登録、署名プロキシの実稼働はまだ行っていません。
このZIPのアップロードだけでは車載ナビへの実送信は始まりません。

## 必要な接続設定

1. https://developer.tesla.com/ で開発者アプリを登録します。
2. TeslaのOAuthで所有者のアクセス許可を取得します。車両コマンドの権限が必要です。
   https://developer.tesla.com/docs/fleet-api/authentication/overview
   パスワードをこのWebアプリに入力する方式ではありません。
3. 署名用の秘密鍵を作成し、公開鍵をドメインで公開、Partner登録を行います。
   https://developer.tesla.com/docs/fleet-api/virtual-keys/developer-guide
4. iPhoneのTeslaアプリで仮想キーを2026年式Model 3に登録します。
5. `navigation_waypoints_request` に対応した署名プロキシを稼働させます。
6. 中継用RenderサービスのEnvironmentに、下記を設定します。

| 環境変数 | 内容 |
|---|---|
| TESLA_COMMAND_PROXY_URL | 信頼できる署名プロキシのHTTPS URL。Fleet API本体のURLではありません |
| TESLA_ACCESS_TOKEN | 所有者OAuthのアクセストークン。期限切れ時は更新が必要 |
| TESLA_VIN | 対象Model 3の17文字VIN。ブラウザから送信先車両は変更できません |
| TESLA_OWNER_SECRET | 自分で生成した32文字以上の十分にランダムな所有者用送信キー |

所有者キーは、例えばPythonの `secrets.token_urlsafe(32)` で生成できます。
本版は個人試験向けの環境変数方式です。OAuthトークンの自動更新・アプリ内ログインは未実装。
トークン・秘密鍵・所有者キーはGitHubへアップロードしないでください。
署名用秘密鍵は署名プロキシにのみ配置し、中継API・ブラウザには配布しません。

## 標準プロキシの制約と対応版

調査したTesla公式 `teslamotors/vehicle-command` のmainには、経由地コマンドの実装がありません。
公式の `tesla/vehicle-command:latest` を起動するだけでは、この機能が動くとは限りません。
公式リポジトリのPR #443には対応実装がありますが、未マージの提案です。
https://github.com/teslamotors/vehicle-command/pull/443

`tesla-proxy/Dockerfile` は、その提案の特定コミット
`281b3a70caaef258e2f7dfe0136a2a192b8cb017` を使用する任意の構築例です。
公式リリースとして扱わないでください。こちらではDockerビルド・実車試験は未実施です。

利用する場合はDockerホスト上で：

```
docker build -t tesla-waypoint-proxy ./tesla-proxy
docker run --rm --security-opt=no-new-privileges:true -v /absolute/config:/config:ro -p 4443:4443 tesla-waypoint-proxy
```

`/absolute/config` には署名用 `fleet-key.pem`、サーバーTLS用 `tls-key.pem` と `tls-cert.pem` を置きます。
コンテナのUID 65532が読める権限で配置します。TLS証明書は接続するドメインと一致する有効な証明書が必要です。
Renderの中継APIから到達できるHTTPSホストに配置してください。ローカルPCのlocalhostには到達できません。
この署名プロキシはTLSで待ち受けます。Render Web Serviceの通常のHTTP待受設定にそのまま流用しないでください。
適切なHTTPSホストまたはTLSアップストリーム対応の構成が必要です。
証明書検証を無効化する実装は入れていません。

## Google Place ID

送信形式は、経由地 → 目的地の順に `refId:<Google Place ID>` をカンマ区切りで並べた文字列です。
OpenStreetMapの検索だけではGoogle Place IDは得られません。
Google地図のAPIキーを設定して検索した地点にはPlace IDを保持します。
地図タップ・座標入力の場合は各地点のPlace IDを別途入力してください。
Google Place IDの確認ツール：
https://developers.google.com/maps/documentation/javascript/examples/places-placeid-finder
APIキーや地点情報を設定したあと「経由地・目的地を画面へ共有」を押して反映します。

## 実際の送信

1. iPhoneで初回の所有者端末登録を行う（v5のREADME参照）。車載側にはキー入力不要。
2. 地点一覧を共有し、車載画面と順序が同じか確認。
3. 「共有済みの地点一覧をTeslaへ送信」を押す。
4. または「ナビ開始時にTesla標準ナビにも送信」をチェックし「ナビ開始」。
5. APIの受付成功表示後も、テスラ標準ナビで経由順を確認。

Web側は地点を送るだけで、Teslaが道路の経路や充電計画を再計算します。
Google/OSRMと同じ道を通る保証はありません。
所有者キー自体は保存しません。v5は30日有効の署名付き端末認証情報をiPhoneへ保存し、再入力を省略します。
位置共有コードのみで車両にコマンドを送れない設計です。初回確認済みのiPhoneが許可した車載端末だけが追加入力なしで送信できます。
送信は順序を保った1つのコマンドで、地点の自動並べ替えは行いません。
同じ地点一覧へのボタン連打は同じ送信IDとして扱い、サーバーは1回のみ外部送信します。
通信タイムアウトでも自動再送はしません。車載ナビを確認してください。
再送が必要なら地点一覧をもう一度共有して新しい版にし、状況を確認してから送信します。
サーバー再起動後の重複排除は保持されませんが、位置共有セッションも同時に失効します。
