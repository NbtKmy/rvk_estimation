# RVK MARCXML 構造リファレンス

ソース:
- https://www.loc.gov/marc/classification/ (MARC 21 Format for Classification Data)
- https://rvk.uni-regensburg.de/api_2.0/marcxml.html (RVK MARCXML API仕様)

ファイル: `rvko_marcxml_2025_4.xml`

---

## 1. ルート構造

```xml
<collection
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.loc.gov/MARC21/slim http://www.loc.gov/standards/marcxml/schema/MARC21slim.xsd"
  xmlns="http://www.loc.gov/MARC21/slim">
  <record> ... </record>
  <record> ... </record>
  ...
</collection>
```

各RVK分類項目が1つの `<record>` に対応する。

---

## 2. レコード構造

各 `<record>` は以下の要素で構成される:

```xml
<record>
  <leader>...</leader>
  <controlfield tag="001">...</controlfield>
  <controlfield tag="003">...</controlfield>
  <controlfield tag="005">...</controlfield>
  <controlfield tag="008">...</controlfield>
  <datafield tag="040" ind1=" " ind2=" ">...</datafield>
  <datafield tag="084" ind1="0" ind2=" ">...</datafield>
  <datafield tag="153" ind1=" " ind2=" ">...</datafield>
  <!-- 任意: 253, 684, 700, 710, 711, 730, 748, 750, 751 -->
</record>
```

---

## 3. Leader (リーダー)

固定長24文字の制御フィールド。

例: `     nw  a22     o  4500`

| 位置 | 意味 | 値 (RVK) |
|------|------|---------|
| 05 | レコードステータス | `n` = 新規, `c` = 修正 |
| 06 | レコードタイプ | `w` = 分類レコード |
| 09 | 文字エンコーディング | `a` = Unicode/UTF-8 |
| 17 | エンコーディングレベル | `o` |

---

## 4. Controlfields (制御フィールド)

### tag="001" — レコード識別子

RVKレコードの一意ID。

| 形式 | 意味 |
|------|------|
| `1:` | 上位クラス (`:` の前が分類レベル深度) |
| `4:2640` | 葉ノード (`:` の後がRVK内部ID) |
| `8:` | ルート直下の主要クラス |

例:
```xml
<controlfield tag="001">1:</controlfield>        <!-- 最上位クラス "A" -->
<controlfield tag="001">4:2640</controlfield>     <!-- 末端ノード -->
```

### tag="003" — 組織コード

```xml
<controlfield tag="003">DE-625</controlfield>
```
`DE-625` = Universitätsbibliothek Regensburg (レーゲンスブルク大学図書館)。常に固定値。

### tag="005" — 最終更新日時

```xml
<controlfield tag="005">202512152015.3</controlfield>
```
形式: `YYYYMMDDHHMMSS.F`（例: 2025年12月15日 20:15）

### tag="008" — 固定長データ

```xml
<controlfield tag="008">120705an|aznnaabbn           | anc    |c</controlfield>
```

| 位置 | 意味 | 値 |
|------|------|----|
| 00-05 | 作成日 (YYMMDD) | `120705` = 2012-07-05 |
| 06 | 分類タイプ | `a` = 単一発行機関用 |
| 07 | 定義済み分類か | `n` = なし |
| 08 | 表記体系 | `\|` = 未指定 |
| 09 | 記号タイプ | `a` = アルファベット |

---

## 5. Datafields (データフィールド)

### tag="040" — カタログ情報

```xml
<datafield tag="040" ind1=" " ind2=" ">
  <subfield code="a">DE-625</subfield>  <!-- 元レコード作成機関 -->
  <subfield code="b">ger</subfield>     <!-- 言語 (German) -->
  <subfield code="c">DE-625</subfield>  <!-- 転写機関 -->
  <subfield code="d">DE-625</subfield>  <!-- 修正機関 -->
</datafield>
```

常に固定値。すべてのレコードに存在する。

---

### tag="084" — 分類体系識別子

```xml
<datafield tag="084" ind1="0" ind2=" ">
  <subfield code="a">rvk</subfield>
</datafield>
```

- `ind1="0"` = 分類体系コードが `$a` に入っている
- `$a` = `rvk` (Regensburger Verbundklassifikation) 常に固定値

---

### tag="153" — 分類記号と階層 ★ 最重要フィールド

RVKノーテーション・名称・階層情報を持つ中核フィールド。

| サブフィールド | 意味 | 備考 |
|--------------|------|------|
| `$a` | 分類記号（開始） | 例: `AA 10000` |
| `$c` | 分類記号（終了） | 範囲ノードの場合のみ。例: `AA 19900` |
| `$j` | 分類項目の名称（ラベル） | ドイツ語 |
| `$e` | 親の分類記号（階層上位、開始） | 繰り返し可。上位から下位の順 |
| `$f` | 親の分類記号（階層上位、終了） | `$e` が範囲の場合に対応 |
| `$h` | 親の名称（`$e`/`$f` に対応） | 繰り返し可 |

#### ケース1: 単一ノーテーション（最上位クラス）

```xml
<datafield tag="153" ind1=" " ind2=" ">
  <subfield code="a">A</subfield>
  <subfield code="j">Allgemeines</subfield>
</datafield>
```
→ 親なし。最上位クラス。

#### ケース2: 親1階層

```xml
<datafield tag="153" ind1=" " ind2=" ">
  <subfield code="a">AA</subfield>
  <subfield code="j">Bibliografien der Bibliografien, ...</subfield>
  <subfield code="e">A</subfield>
  <subfield code="h">Allgemeines</subfield>
</datafield>
```
→ `AA` の親は `A`（Allgemeines）

#### ケース3: 範囲ノーテーション + 多階層

```xml
<datafield tag="153" ind1=" " ind2=" ">
  <subfield code="a">AA 10000</subfield>
  <subfield code="c">AA 19900</subfield>
  <subfield code="j">Bibliografien der Bibliografien</subfield>
  <subfield code="e">A</subfield>
  <subfield code="h">Allgemeines</subfield>
  <subfield code="e">AA</subfield>
  <subfield code="h">Bibliografien der Bibliografien, ...</subfield>
</datafield>
```
→ `AA 10000`–`AA 19900` の範囲。親は `A` → `AA` の順（昇順）。

#### ケース4: 葉ノード（末端ノーテーション）

```xml
<datafield tag="153" ind1=" " ind2=" ">
  <subfield code="a">AA 10100</subfield>
  <subfield code="j">Antike Welt</subfield>
  <subfield code="e">A</subfield>
  <subfield code="h">Allgemeines</subfield>
  <subfield code="e">AA</subfield>
  <subfield code="h">Bibliografien der Bibliografien, ...</subfield>
  <subfield code="e">AA 10000</subfield>
  <subfield code="f">AA 19900</subfield>
  <subfield code="h">Bibliografien der Bibliografien</subfield>
</datafield>
```
→ `$e`/`$f` のペアが範囲親を示す。

**階層の読み方:**
- `$e` + `$h` のペアを繰り返しで並べると、最上位から当該ノードまでのパスが順に並ぶ
- `$c` がある場合 = 範囲ノード（`$a` ≤ ノーテーション ≤ `$c`）
- `$c` がない場合 = 単一ノーテーション

---

### tag="253" — 参照注記（Complex See Reference）

ユーザーを他のノーテーションへ誘導する注記。

```xml
<datafield tag="253" ind1="0" ind2=" ">
  <subfield code="i">(aber Film allein siehe AP 43100)</subfield>
</datafield>
```

| インジケータ | 意味 |
|------------|------|
| `ind1="0"` | 参照指示 |
| `$i` | 注記テキスト（自由文） |

---

### tag="684" — 補助注記（Auxiliary Instruction Note）

分類付与の説明・注意事項。

```xml
<datafield tag="684" ind1="1" ind2=" ">
  <subfield code="i">Erläuterungen zur Notationsvergabe s. RVK-Online - Nutzungshinweise</subfield>
</datafield>
```

| インジケータ | 意味 |
|------------|------|
| `ind1="1"` | 説明注記 |
| `$i` | 注記テキスト（自由文） |

---

### tag="700"–"751" — 索引語フィールド（GNDリンク）

RVK分類項目と関連するGND（Gemeinsame Normdatei）典拠語を記述する。

#### 共通サブフィールド構造

```xml
<subfield code="0">(DE-588)4006432-3</subfield>  <!-- GND識別子 -->
<subfield code="a">Bibliografie</subfield>         <!-- 典拠形ラベル -->
<subfield code="2">gnd</subfield>                  <!-- 典拠ソース = GND -->
```

#### フィールド別詳細

| タグ | 種別 | ind1 | 例 |
|-----|------|------|-----|
| `700` | 個人名 | `1`=姓名順, `3`=家族名 | `Goethe, Johann Wolfgang von` |
| `710` | 団体名 | `2` | 企業・機関名 |
| `711` | 会議・イベント名 | — | 学会・会議名 |
| `730` | 統一タイトル | — | 作品名 |
| `748` | 年代語 | — | 時代・世紀 |
| `750` | 主題語（トピカル） | `1`=7xx ind1 | 一般主題語 |
| `751` | 地名 | — | 地理的名称 |

#### ind2 の意味（全7XXフィールド共通）

| ind2 | 意味 |
|------|------|
| `7` | `$2` で指定した典拠ソースを使用（= `gnd`） |

#### 実例

```xml
<!-- 主題語 (750) -->
<datafield tag="750" ind1="1" ind2="7">
  <subfield code="0">(DE-588)4145270-7</subfield>
  <subfield code="a">Bibliothekskatalog</subfield>
  <subfield code="2">gnd</subfield>
</datafield>

<!-- 地名 (751) -->
<datafield tag="751" ind1=" " ind2="7">
  <subfield code="0">(DE-588)4014770-8</subfield>
  <subfield code="a">England</subfield>
  <subfield code="2">gnd</subfield>
</datafield>
```

---

## 6. フィールド出現頻度サマリー

| タグ | 必須/任意 | 繰り返し | 説明 |
|-----|---------|--------|------|
| leader | 必須 | × | レコードメタ情報 |
| 001 | 必須 | × | レコードID |
| 003 | 必須 | × | 機関コード（常に `DE-625`） |
| 005 | 必須 | × | 最終更新日時 |
| 008 | 必須 | × | 固定長データ |
| 040 | 必須 | × | カタログ情報 |
| 084 | 必須 | × | 分類体系 `rvk` |
| 153 | 必須 | × | **ノーテーション・階層** ★ |
| 253 | 任意 | ○ | 参照注記 |
| 684 | 任意 | ○ | 補助注記 |
| 700 | 任意 | ○ | 個人名索引語 |
| 710 | 任意 | ○ | 団体名索引語 |
| 711 | 任意 | ○ | 会議名索引語 |
| 730 | 任意 | ○ | 統一タイトル索引語 |
| 748 | 任意 | ○ | 年代語索引語 |
| 750 | 任意 | ○ | 主題語索引語 |
| 751 | 任意 | ○ | 地名索引語 |

---

## 7. 階層構造の導出方法

### 親子関係の判定

1. `$a` (と `$c`) が当該ノードのノーテーション
2. `$e`/`$h` ペアの最後が直接の親
3. `$e`/`$h` ペアを順に辿ることで完全なパスを再現できる

### 範囲ノードと葉ノードの区別

- `$c` あり → 範囲ノード（他ノードの親になれる）
- `$c` なし → 葉ノードまたは単一ポイントノード

### 完全パス例

```
A (Allgemeines)
└─ AA (Bibliografien der Bibliografien, ...)
   └─ [AA 10000–AA 19900] (Bibliografien der Bibliografien)
      └─ AA 10100 (Antike Welt)
```

---

## 8. 注意事項

- **更新レコード**: 更新配信時、上位階層の変更はすべての子孫レコードにも修正レコードとして配信される
- **GND識別子形式**: `(DE-588)XXXXXXXXX-X` — ハイフンと1桁チェックデジット付き
- **ノーテーション形式**: 1–2文字のアルファベット（大文字）＋スペース＋5桁数字（例: `AA 10000`）。最上位は1–2文字のみ（例: `A`, `AA`）
- **言語**: すべての名称・注記はドイツ語
