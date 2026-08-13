# EvidenceRadar-Editions

> 以「期刊 × 月份／期別」為第一級索引，直接從公開來源重建文獻集合，生成繁中互動 HTML，並保存成可瀏覽的 GitHub Pages 刊物資料庫。

EvidenceRadar-Editions 是 EvidenceRadar 的 sibling runner。它可以參考 EvidenceRadar 的 source/config 定義與 pin 住的 upstream commit，但**不使用 EvidenceRadar 的 Report、Run、Evidence、State、Work Pack 或 Pages 產出作為自己的資料來源**。

```text
EvidenceRadar source/config hints       PubMed / Europe PMC / Crossref
                 │                                  │
                 └──────────────┐     ┌─────────────┘
                                ▼     ▼
                     scoped acquisition runner
                                │
                  journal + inclusive date window
                                │
                    identity reconciliation / dedup
                                │
                       canonical edition JSON
                                │
                   zh-TW translation handoff
                                │
                  validated publishable bundle
                                │
                                ▼
                    sharded canonical Git store
                                │
                deterministic Pages-time rendering
                                ▼
                     GitHub Pages portal
```

## Storage v0.3

Git tree 不再永久保存每一期 HTML 與重複 aliases。正式 publication store 是：

```text
catalog/
  journals.json

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

## 1. 生成指定期刊刊物

```sh
evidenceradar-editions run \
  --journal "JAMA Network Open" \
  --issn 2574-3805 \
  --slug jama-network-open \
  --start 2026-08-01 \
  --end 2026-08-14 \
  --period-kind month \
  --revision 1 \
  --radar-root ../EvidenceRadar \
  --radar-commit 6da659df845e4b76072dae016120ca76ed9c27c4 \
  --translation-request dist/jama-2026-08/raw/EvidenceRadar_Editions__jama-network-open__2026-08__r01.translation-request.zh-TW.json \
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

同一個 period/revision 的相同 bytes 可重複 publish；不同 bytes 不可覆寫，必須增加 revision。

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
  links.json
  journals/<journal>/index.html
  journals/<journal>/<period>/index.html
  journals/<journal>/<period>/rXX/index.html
```

首頁是期刊總表；點入期刊後是月份／期別表，再進 revision 與完整互動 HTML。文章搜尋索引只取各期別最新 revision。

`.github/workflows/pages.yml` 只在 build/deploy 時生成 HTML，不把 `_site` 或 HTML 回寫 Git。Repository 的 Pages Source 需一次性設定為 **GitHub Actions**。

## 互動 HTML 的資料界線

HTML 提供搜尋、filter、排序與 navigation，不把「出現在索引」升格為「已讀全文」或「科學結論已核實」。繁中 summary 的 basis 會直接顯示：

- `TITLE_ONLY`：依題名整理，未核實研究結果。
- `METADATA`：依書目／索引資料整理。
- `ABSTRACT`：依摘要整理。
- `FULL_TEXT`：依實際取得的全文整理。

這個 repo 是 bibliographic publication/archive system，不取代 EvidenceRadar 的 claim-level evidence governance。

## CI

```sh
python -m compileall -q evidenceradar_editions tests
python -m unittest discover -s tests -v
python -m evidenceradar_editions --help
```

CI 在 Python 3.11、3.12、3.13 執行，並驗證 canonical store 不含 HTML、月份 sharding、immutability，以及 Pages 可從 JSON 重建互動報告。

## Open source

- Apache-2.0：程式碼、測試、validator、executable config 與 automation。
- CC BY 4.0：本 repo 原創文件、報告文字／版面與選編安排。
- 第三方文章題名、作者、期刊名稱、識別碼、metadata、摘要、全文與 publisher assets 不因本 repo 開源而被重新授權。

詳見 [`docs/OPEN_SOURCE.md`](docs/OPEN_SOURCE.md)、[`NOTICE.md`](NOTICE.md)、[`LICENSE-CONTENT.md`](LICENSE-CONTENT.md)、[`SECURITY.md`](SECURITY.md) 與 [`GOVERNANCE.md`](GOVERNANCE.md)。
