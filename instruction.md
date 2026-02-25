# RVK Notation RAG 実装指示書

## 概要

RVK（Regensburger Verbundklassifikation）のMARCXMLダンプから、
LLMによるノーテーション推測を支援するRAGシステムを構築する。

- **入力ファイル**: `rvko_marcxml_2025_4.xml`（約78万3千件）
- **埋め込みモデル**: Ollama `bge-m3`（1024次元ベクトル）
- **ベクトルDB**: Qdrant（`docker-compose.yml` で起動済み、`localhost:6333`）
- **言語**: Python（uv で環境管理）

---

## ステップ1: XMLパース → embedding_text + payload の生成

### ターゲットフィールド（tag="153"）

| サブフィールド | 内容 | 必須 |
|---|---|---|
| `$a` | ノーテーション（開始） | ✅ |
| `$c` | ノーテーション（終了）※範囲ノードのみ | |
| `$j` | 分類項目ラベル | ✅ |
| `$e` | 親ノーテーション（繰り返し、昇順） | ✅ |
| `$f` | 親ノーテーション終了（範囲親のみ） | |
| `$h` | 親ラベル（`$e`と対応、繰り返し） | ✅ |

### その他フィールド

| tag | 内容 | サブフィールド |
|---|---|---|
| `750` | 主題語（GND） | `$a`=ラベル, `$0`=GND-ID |
| `751` | 地名（GND） | `$a`=ラベル, `$0`=GND-ID |
| `700` | 個人名（GND） | `$a`=ラベル, `$0`=GND-ID |
| `710` | 団体名（GND） | `$a`=ラベル, `$0`=GND-ID |
| `748` | 年代語（GND） | `$a`=ラベル, `$0`=GND-ID |
| `253` | 参照注記（See also） | `$i`=テキスト |
| `684` | 補助注記（Scope note） | `$i`=テキスト |

---

## ステップ2: embedding_text フォーマット

Ollamaに渡すテキスト（ベクトル化対象）。
階層パスは **直近5階層まで** に絞る（長すぎる場合）。

```
Notation: {$a}[ – {$c}]
Bezeichnung: {$j}
Hierarchie: {$h[0]} > {$h[1]} > ... > {$h[-1]}
Schlagwörter: {GND $a をセミコロン区切り}   ← GNDがある場合のみ
Hinweis: {253/$i + 684/$i を連結}           ← 注記がある場合のみ
```

### 具体例（GNDあり・注記あり）

```
Notation: AK 17000 – AK 17990
Bezeichnung: Wissenschaftsgeschichte einzelner Länder, auch Teilgebiete und Geschichte einzelner Gesellschaften
Hierarchie: Allgemeines > Wissenschaftskunde und Wissenschaftsorganisation > Biografien, Geschichte
Schlagwörter: Geschichte; Wissenschaft; Wissenschaftliche Gesellschaft
Hinweis: sofern nicht bei AK 51000 ff. Emigration s. AK 29500; (LS 2)
```

### 具体例（GNDなし・注記なし）

```
Notation: AA 10100
Bezeichnung: Antike Welt
Hierarchie: Allgemeines > Bibliografien der Bibliografien, Universalbibliografien... > Bibliografien der Bibliografien
```

---

## ステップ3: Payload スキーマ（Qdrantに保存するメタデータ）

```json
{
  "notation":       "AK 17000",
  "notation_end":   "AK 17990",        // null if not range
  "label":          "Wissenschaftsgeschichte einzelner Länder...",
  "is_range":       true,
  "hierarchy": [
    {"notation": "A",  "notation_end": null, "label": "Allgemeines"},
    {"notation": "AK 10000", "notation_end": "AK 79999", "label": "Wissenschaftskunde..."},
    {"notation": "AK 16000", "notation_end": "AK 18600", "label": "Biografien, Geschichte"}
  ],
  "breadcrumb":     "Allgemeines > Wissenschaftskunde... > Biografien, Geschichte",
  "gnd_terms":      ["Geschichte", "Wissenschaft"],
  "gnd_ids":        ["(DE-588)4020517-4", "(DE-588)4066562-8"],
  "gnd_types":      ["750", "750"],    // tag番号: 750/751/700/710/748
  "see_also":       "sofern nicht bei AK 51000 ff.",  // 253
  "usage_note":     "(LS 2)",          // 684
  "record_id":      "2536:1651"        // controlfield tag="001"
}
```

---

## ステップ4: Qdrant コレクション設定

- **コレクション名**: `rvk`
- **ベクトル次元**: `1024`（bge-m3 の dense vector 次元数）
- **距離関数**: `Cosine`
- **インデックス**: `HNSW`（デフォルト）

Point の ID は `record_id` の数値部分（コロン以降）を整数として使う。
ただし `1:`, `2:` など数値がない場合は別途採番する（連番整数）。

---

## ステップ5: 処理フロー（Pythonスクリプト）

```
build_dataset.py
│
├─ parse_xml()          lxml の iterparse で XML をストリーム処理
│   └─ yield (embedding_text, payload) per record
│
├─ embed_batch()        Ollama REST API に POST
│   │  POST http://localhost:11434/api/embed
│   │  Body: {"model": "bge-m3", "input": ["text1", "text2", ...]}
│   └─ return [[float]*1024, ...]
│
└─ upsert_to_qdrant()   qdrant-client で バッチ upsert
    └─ client.upsert(collection_name="rvk", points=[...])
```

### バッチ処理の方針

- XMLはストリーム読み込み（lxmlの`iterparse`）でメモリを節約
- Ollamaへのリクエスト: **バッチサイズ 32〜64** で送る
- Qdrantへのupsert: **バッチサイズ 256** で送る
- 進捗表示: `tqdm` で件数と推定残り時間を表示
- 中断・再開: upsertは冪等なので再実行可能（上書き）

---

## 必要なPythonライブラリ

```
lxml          # 高速XMLパーサー（ElementTreeより速い）
qdrant-client # Qdrant Python クライアント
httpx         # Ollama REST API 呼び出し用（非同期対応）
tqdm          # プログレスバー
loguru        # ロギング
```

### uv でのインストールコマンド例

```bash
uv init
uv add lxml qdrant-client httpx tqdm loguru
```

---

## ファイル構成（想定）

```
rvk_estimation/
├── docker-compose.yml
├── instruction.md          ← このファイル
├── rvko_marcxml_2025_4.xml
├── rvk_xml_structure.md
├── pyproject.toml          ← uv init後に生成
└── build_dataset.py        ← メインスクリプト（実装対象）
```

---

## 実行方法

```bash
# 1. Qdrant を起動
docker-compose up -d

# 2. bge-m3 モデルを取得（初回のみ）
ollama pull bge-m3

# 3. パイプライン実行
caffeinate uv run build_dataset.py
```

中断後の再実行は upsert が冪等なので安全に上書きされる。

---

## 備考

- bge-m3 は多言語対応・ドイツ語も高精度
- Qdrant の `localhost:6333` はHTTP REST、`6334` はgRPC
- qdrant-client はデフォルトでHTTP RESTを使う（明示しなくてOK）
- 78万件 × bge-m3 の埋め込み時間の目安: CPUのみで数時間〜十数時間。
  GPU(CUDA/Metal)があれば大幅に短縮。
