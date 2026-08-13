# EvidenceRadar-Editions

> 以「期刊 × 時間」為第一級索引，直接從公開來源重建文獻集合，生成繁中互動 HTML，並保存成可瀏覽的 GitHub Pages 刊物資料庫。

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
                   zh-TW translation handoff contract
                                │
          ┌─────────────────────┴─────────────────────┐
          ▼                                           ▼
Radar-like standalone HTML                  immutable edition archive
                                                      │
                                                      ▼
                                            GitHub Pages portal
```

## v0.2 交付內容

- 指定期刊、ISSN、日期範圍與 revision，直接查詢 PubMed、Europe PMC、Crossref。
- 每個來源回傳後再次執行 journal／ISSN／日期 scope filter；保留 DAY／MONTH／YEAR 日期精度，避免把不精確日期假裝成某一天。
- DOI → PMID → PMCID → 題名＋日期的 identity reconciliation。
- 自描述檔名，不再輸出一堆無法分辨的 `EvidenceRadar_Edition.html`。
- 繁中為主要閱讀語言，保留原文題名。
- hash-bound TranslationRequest／TranslationResponse；不需要在 GitHub Actions 裡藏翻譯 API key。
- Radar-like 互動 HTML：全文搜尋、文章類型、來源、日期、DOI／PMID／PMCID、翻譯狀態、排序、展開／收合。
- source receipt 顯式區分 SUCCESS／NO_RESULTS／PARTIAL／FAILED／NOT_ATTEMPTED，截斷結果不能冒充完整。
- canonical JSON → HTML byte parity validator，禁止只手改 HTML。
- immutable archive：`journal / period / revision`。
- GitHub Pages 總覽：可搜尋已發布刊物與文章，並點入每一期完整互動 HTML。

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
  --end 2026-08-31 \
  --period-kind month \
  --revision 1 \
  --radar-root ../EvidenceRadar \
  --radar-commit 6da659df845e4b76072dae016120ca76ed9c27c4 \
  --translation-request dist/jama-2026-08/raw/EvidenceRadar_Editions__jama-network-open__2026-08__r01.translation-request.zh-TW.json \
  --output-dir dist/jama-2026-08/raw
```

完整月刊的輸出名稱會是：

```text
EvidenceRadar_Editions__jama-network-open__2026-08__r01.html
EvidenceRadar_Editions__jama-network-open__2026-08__r01.json
EvidenceRadar_Editions__jama-network-open__2026-08__r01.manifest.json
```

若範圍是 `2026-08-01 → 2026-08-14`，period key 會明確寫成 `2026-08-01--2026-08-14`，不會冒充完整八月月刊。

重建語義固定是：

> current-source reconstruction of the historical publication window

亦即「現在的來源如何描述該歷史出版範圍」，不是「當時 Radar 曾看見什麼」。

## 2. 產生與套用繁中翻譯

TranslationRequest 採與刊物相同的 self-describing stem，保留原文題名、識別碼與 source URLs，不把 publisher PDF 或原始全文塞進 repo。

```sh
evidenceradar-editions translation-request \
  --bundle-dir dist/jama-2026-08/raw \
  --output dist/jama-2026-08/EvidenceRadar_Editions__jama-network-open__2026-08__r01.translation-request.zh-TW.json
```

翻譯回應必須同時綁定來源 edition JSON 的 SHA-256 與 deterministic request binding SHA-256，並為每篇提供：

```json
{
  "canonical_id": "doi:10.1001/example",
  "title_zh_tw": "繁中題名",
  "summary_zh_tw": "不捏造結果的繁中導讀。",
  "basis": "TITLE_ONLY"
}
```

`basis` 只可使用 `TITLE_ONLY`、`METADATA`、`ABSTRACT`、`FULL_TEXT`；不能把只看題名寫成全文核實。

```sh
evidenceradar-editions apply-translation \
  --bundle-dir dist/jama-2026-08/raw \
  --response dist/jama-2026-08/EvidenceRadar_Editions__jama-network-open__2026-08__r01.translation-response.zh-TW.json \
  --output-dir dist/jama-2026-08/publishable
```

正式出版 gate：

```sh
evidenceradar-editions validate \
  --bundle-dir dist/jama-2026-08/publishable \
  --require-zh-tw
```

## 3. 保存到 immutable archive

```sh
evidenceradar-editions publish \
  --bundle-dir dist/jama-2026-08/publishable \
  --archive-root archive
```

歸檔結構：

```text
archive/
  journals/
    jama-network-open/
      2026-08/
        r01/
          index.html
          edition.json
          manifest.json
          EvidenceRadar_Editions__jama-network-open__2026-08__r01.html
          EvidenceRadar_Editions__jama-network-open__2026-08__r01.json
          EvidenceRadar_Editions__jama-network-open__2026-08__r01.manifest.json
```

同一個 period 的不同 bytes 不可覆寫既有 revision；必須建立 `r02`。完全相同的 bundle 重複 publish 則是 idempotent。

## 4. 建立 GitHub Pages 總覽

```sh
evidenceradar-editions build-pages \
  --archive-root archive \
  --repository hoiyu915-droid/EvidenceRadar-Editions \
  --output-dir _site
```

Pages 產物包含：

```text
_site/
  index.html             # 所有期刊與期數總覽
  index.json             # edition catalog
  search-index.json      # article-level 搜尋索引
  links.json
  journals/<journal>/<period>/index.html
  journals/<journal>/<period>/rXX/index.html
```

首頁可依期刊、期間類型與關鍵字篩選；輸入文章題名、DOI 或 PMID 時會查詢文章索引，並直接連到該期刊物。

`.github/workflows/pages.yml` 在 `main` 的 archive 或 Pages code 變動時建置並部署。Repository 必須把 **Settings → Pages → Build and deployment** 設為 **GitHub Actions**；workflow 會先嘗試啟用，若 token 權限不足則 fail closed 並指出這個一次性設定。

## 互動 HTML 的資料界線

HTML 是 canonical edition JSON 的 deterministic projection。它提供 navigation／filter，不把「出現在索引」偷偷升格為「已讀全文」或「科學結論已核實」。

繁中 summary 的 `basis` 會直接顯示：

- `TITLE_ONLY`：依題名整理，未核實研究結果。
- `METADATA`：依書目／索引資料整理。
- `ABSTRACT`：依摘要整理。
- `FULL_TEXT`：依實際取得的全文整理。

這個 repo 是 bibliographic publication/archive system，不取代 EvidenceRadar 的 claim-level evidence governance。

## CI 與 live runner

```sh
python -m compileall -q evidenceradar_editions tests
python -m unittest discover -s tests -v
python -m evidenceradar_editions --help
```

CI 在 Python 3.11、3.12、3.13 執行。`.github/workflows/live-edition.yml` 是 read-only manual runner：直接查來源、生成 self-describing bundle 與 TranslationRequest，再上傳短期 Actions artifact；它不會自動把未翻譯內容出版到 Pages。

## Open source

- Apache-2.0：程式碼、測試、validator、executable config 與 automation。
- CC BY 4.0：本 repo 原創文件、報告文字／版面與選編安排。
- 第三方文章題名、作者、期刊名稱、識別碼、metadata、摘要、全文與 publisher assets 不因本 repo 開源而被重新授權。

詳見 [`docs/OPEN_SOURCE.md`](docs/OPEN_SOURCE.md)、[`NOTICE.md`](NOTICE.md)、[`LICENSE-CONTENT.md`](LICENSE-CONTENT.md)、[`SECURITY.md`](SECURITY.md) 與 [`GOVERNANCE.md`](GOVERNANCE.md)。
