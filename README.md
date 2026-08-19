# EvidenceRadar-Editions

> 以「期刊 × 月份／期別」為第一級索引，直接從公開來源重建文獻集合，生成繁中互動 HTML，並保存成可瀏覽的 GitHub Pages 刊物資料庫。

EvidenceRadar-Editions 是 EvidenceRadar 的 sibling runner。它可以參考 EvidenceRadar 的 source/config 定義與 pin 住的 upstream commit，但**不使用 EvidenceRadar 的 Report、Run、Evidence、State、Work Pack 或 Pages 產出作為自己的資料來源**。

```text
EvidenceRadar source/config hints       PubMed / Europe PMC / Crossref
                 │                                  │
                 └──────────────┐     ┌─────────────┘
                                ▼     ▼
                     journal processing policy
                      FULL / TRIAGE / INDEX_ONLY
                                │
                     scoped metadata acquisition
                                │
                  journal + inclusive date window
                                │
                    identity reconciliation / dedup
                                │
                       canonical edition JSON
                                │
                 selective zh-TW translation handoff
                                │
                  validated publishable bundle
                                │
                                ▼
                    sharded canonical Git store
                                │
                volume-aware Pages-time projection
                                ▼
                     GitHub Pages portal
```

## 2026 年 8 月 production status

Authoritative August registry coverage 已完成至 **2026-08-14 UTC**：58/58 本都有 terminal outcome，包含 52 本 `PUBLISHED`（4,389 筆 records）、4 本 `NO_MATCHING_ARTICLES`、2 本 `OUTSIDE_WINDOW`，以及 0 個 unresolved date-evidence gap。

Exact production corpus 在 SHA `6b09654c4e171128f1e52f430cb26c725b7caf79` 上包含 61 個 journal slugs、63 periods、64 revisions 與 4,415 筆 canonical records；abstract/full-text/evidence funnel、六個 no-edition outcomes、Chemical Science repair、跨刊 synthesis 與 workflow/artifact digests 見 [`docs/AUGUST_2026_COMPLETION.md`](docs/AUGUST_2026_COMPLETION.md)。

這是 **August MTD**，不是 `FINAL`。完整 8 月只能在 2026-08-31 結束後以新 revision 重建；不為追求日期更新而把已完成的 58 本無差別重跑成 r02。

## Storage v0.3

Git tree 不再永久保存每一期 HTML 與重複 aliases。正式 publication store 是：

```text
catalog/
  journals.json
  processing-policies.json

editions/
  <journal-slug>/
    <YYYY>/
      <MM>/
        r01/
          edition.json
          manifest.json
          storage.json
        r02/
          ...
```

完整月刊與 MTD 月刊都使用同一個 `YYYY/MM` 邏輯位置；月底重新重建時增加 revision，而不是建立另一個日期範圍資料夾。

非月刊 period 仍可保存，但不會污染月份 slot：

```text
editions/<journal>/<YYYY>/<MM>/days/<DD>/rXX/
editions/<journal>/<ISO-YYYY>/weeks/Wxx/rXX/
editions/<journal>/<YYYY>/ranges/<period-key>/rXX/
```

HTML 是 canonical edition JSON 的 deterministic projection。`editions/` 不保存 HTML；GitHub Pages build 時才在 runner 暫時重建 HTML、下載檔名與 navigation surface。這避免數十本期刊 × 多年月 × revisions 把 Git history 膨脹成 presentation dump。

舊 `archive/` 介面只保留作 v0.2 compatibility；production CLI 與 Pages workflow 預設走 `editions/`。

## 安裝

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

支援 Python 3.11–3.13。

## Volume-aware processing

`catalog/processing-policies.json` 將期刊 workload 分成：

- `FULL`：正常 metadata acquisition，允許自動翻譯 handoff；
- `TRIAGE`：保留 bounded metadata coverage，但延後全量翻譯／短評；
- `INDEX_ONLY`：只做 metadata index，不自動展開 editorial work；
- `SUSPENDED`：在任何 source adapter 被呼叫前停止新的 acquisition，歷史 edition 不刪除。

來源 adapter 現階段抓的是 bibliographic metadata，不是逐篇 PDF。Policy 同時限制 per-source records、translation handoff 與 Pages browser projection；它不把 metadata 冒充全文核實，也不按期刊產量改寫證據力。

`FULL` journal 若 source reported total 超過容量門檻，該 run 會留下 configured/effective mode，並自動降成 `TRIAGE`；系統不會自動 suspend。大型 edition 的 canonical JSON 仍完整，但 revision 頁的 `browse.json` 只包含 bounded deterministic projection，頁面會明示 canonical／projected／omitted 數量。詳見 [`docs/PROCESSING_POLICIES.md`](docs/PROCESSING_POLICIES.md)。

```sh
python -m evidenceradar_editions journals --processing-mode TRIAGE
python -m evidenceradar_editions journals --processing-mode SUSPENDED
```

## 1. 生成指定期刊刊物

以 registry slug 執行時會自動套用 processing policy：

```sh
evidenceradar-editions run \
  --journal-slug jama-network-open \
  --start 2026-08-01 \
  --end 2026-08-14 \
  --period-kind month \
  --revision 1 \
  --radar-root ../EvidenceRadar \
  --radar-commit 6da659df845e4b76072dae016120ca76ed9c27c4 \
  --translation-request dist/jama-2026-08/raw/EvidenceRadar_Editions__jama-network-open__2026-08__r01.translation-request.zh-TW.json \
  --output-dir dist/jama-2026-08/raw
```

低階顯式 identity 介面仍保留：

```sh
evidenceradar-editions run \
  --journal "JAMA Network Open" \
  --issn 2574-3805 \
  --slug jama-network-open \
  --start 2026-08-01 \
  --end 2026-08-14 \
  --output-dir dist/jama-2026-08/raw
```

`2026-08-01 → 2026-08-14` 配合 `--period-kind month` 會建立邏輯期別 `2026-08`，狀態為 `MTD`；完整到 8 月 31 日時狀態改為 `FINAL`。兩者屬同一月份，不覆寫既有 revision。

重建語義固定是：

> current-source reconstruction of the historical publication window

即「現在的來源如何描述該歷史出版範圍」，不是「當時 Radar 曾看見什麼」。

## 2. 產生與套用繁中翻譯

```sh
evidenceradar-editions translation-request \
  --bundle-dir dist/jama-2026-08/raw \
  --output dist/jama-2026-08/request.zh-TW.json
```

TranslationResponse 必須綁定來源 edition JSON SHA-256 與 deterministic request binding。`basis` 只可使用 `TITLE_ONLY`、`METADATA`、`ABSTRACT`、`FULL_TEXT`，不能把只看題名寫成全文核實。

`TRIAGE` 與 `INDEX_ONLY` 不會由 live workflow 自動替每篇建立 translation request；需要時再顯式執行上面的 command。

```sh
evidenceradar-editions apply-translation \
  --bundle-dir dist/jama-2026-08/raw \
  --response dist/jama-2026-08/response.zh-TW.json \
  --output-dir dist/jama-2026-08/publishable

evidenceradar-editions validate \
  --bundle-dir dist/jama-2026-08/publishable \
  --require-zh-tw
```

## 3. 保存到 canonical editions store

```sh
evidenceradar-editions publish \
  --bundle-dir dist/jama-2026-08/publishable \
  --editions-root editions
```

Metadata-only `TRIAGE`／`INDEX_ONLY` publication 必須顯式使用 `--allow-untranslated`。同一個 period/revision 的相同 bytes 可重複 publish；不同 bytes 不可覆寫，必須增加 revision。

v0.2 legacy archive 仍可顯式使用：

```sh
evidenceradar-editions publish \
  --bundle-dir dist/jama-2026-08/publishable \
  --archive-root archive
```

但這不是 production default，因為它會保存 HTML 與重複 aliases。

## 4. 建立 GitHub Pages 總覽

```sh
evidenceradar-editions build-pages \
  --editions-root editions \
  --catalog-root catalog \
  --repository hoiyu915-droid/EvidenceRadar-Editions \
  --output-dir _site
```

Pages 產物包含：

```text
_site/
  index.html
  index.json
  search-index.json
  processing-policies.json
  links.json
  journals/<journal>/index.html
  journals/<journal>/<period>/index.html
  journals/<journal>/<period>/rXX/index.html
```

首頁是期刊總表；點入期刊後是月份／期別表，再進 revision 與容量感知互動頁。文章搜尋索引只取各期別最新 revision。

`.github/workflows/pages.yml` 只在 build/deploy 時生成 HTML，不把 `_site` 或 HTML 回寫 Git。Repository 的 Pages Source 需一次性設定為 **GitHub Actions**。

## 5. 只補缺少的日期

已存在月刊 revision 時，不必重新向來源查詢整個月份。`backfill` 只取得目前
canonical 月刊結束日之後的連續日期，使用 canonical ID 去重，再建立新的完整月份
snapshot revision：

```sh
evidenceradar-editions backfill \
  --journal-slug acs-central-science \
  --start 2026-08-15 \
  --end 2026-08-19 \
  --revision 2 \
  --editions-root editions \
  --catalog-root catalog \
  --radar-root ../EvidenceRadar \
  --radar-commit 6da659df845e4b76072dae016120ca76ed9c27c4 \
  --output-dir dist/acs-2026-08-r02
```

這個命令不修改 `r01`，也不把 delta 假裝成完整重抓。`r02/edition.json` 會保存
base SHA、舊窗口、新 acquisition 窗口、取得／新增／去重數量與明確的 incremental
semantics。若來源為 `PARTIAL` 或 `SOURCE_ACCESS_GAP`，整個 publication fail closed。

多刊 production request 使用 [`catalog/backfill-request.json`](catalog/backfill-request.json)
與 `incremental-backfill.yml`。Workflow 一次完成所有指定期刊、以單一 guarded PR
發布 canonical revisions，最後只 dispatch 一次 Pages。Pages 仍從 canonical JSON
建立完整靜態 HTML；瀏覽器不需要載入或拼接整個資料庫。

詳見 [`docs/INCREMENTAL_BACKFILL.md`](docs/INCREMENTAL_BACKFILL.md)。

## 互動 HTML 的資料界線

HTML 提供搜尋、filter、排序與 navigation，不把「出現在索引」升格為「已讀全文」或「科學結論已核實」。繁中 summary 的 basis 會直接顯示：

- `TITLE_ONLY`：依題名整理，未核實研究結果。
- `METADATA`：依書目／索引資料整理。
- `ABSTRACT`：依摘要整理。
- `FULL_TEXT`：依實際取得的全文整理。

Pages 的容量投影同樣不是 quality/relevance ranking。完整 canonical metadata 保留在 `edition.json`。

這個 repo 是 bibliographic publication/archive system，不取代 EvidenceRadar 的 claim-level evidence governance。

## CI

```sh
python -m compileall -q evidenceradar_editions tests
python -m unittest discover -s tests -v
python -m evidenceradar_editions --help
```

CI 在 Python 3.11、3.12、3.13 執行，並驗證 canonical store 不含 HTML、月份 sharding、immutability、journal processing policy，以及 Pages 可從 JSON 重建容量感知互動報告。

## Open source

- Apache-2.0：程式碼、測試、validator、executable config 與 automation。
- CC BY 4.0：本 repo 原創文件、報告文字／版面與選編安排。
- 第三方文章題名、作者、期刊名稱、識別碼、metadata、摘要、全文與 publisher assets 不因本 repo 開源而被重新授權。

詳見 [`docs/OPEN_SOURCE.md`](docs/OPEN_SOURCE.md)、[`docs/PROCESSING_POLICIES.md`](docs/PROCESSING_POLICIES.md)、[`NOTICE.md`](NOTICE.md)、[`LICENSE-CONTENT.md`](LICENSE-CONTENT.md)、[`SECURITY.md`](SECURITY.md) 與 [`GOVERNANCE.md`](GOVERNANCE.md)。
