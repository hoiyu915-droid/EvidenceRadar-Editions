# 2026 年 8 月 Editions 完成紀錄

**狀態：August MTD canonical publications 已更新至 2026-08-29 UTC；authoritative terminal-coverage ledger 維持 2026-08-23 UTC**

這份紀錄封存 2026 年 8 月的 authoritative registry coverage、例外處理、跨刊篩選結果與 production 驗證。它不是 8 月 `FINAL`：完整月份只能在 2026-08-31 結束後以新 revision 重建，不能覆寫既有 MTD publication。

### 2026-08-29 incremental publication refresh

全部 78 本已有 August canonical base 的期刊均只查詢缺少的 `2026-08-24..2026-08-29` suffix，再與已驗證的 immutable base 合成新 full-snapshot revision；沒有重新抓取 8/1..23，也沒有覆寫 r01／r03／r04。結果為 9 本 r02、68 本 r04、1 本 r05，全部最新 monthly scope 均結束於 8/29；61 本 core publications 共 7,891 筆 records，17 本 Cambridge provider publications 共 71 筆。

四本沒有 August canonical base 的 registry journals 沒有被這次 suffix backfill 假裝成已重新 probe，因此 [`catalog/coverage/2026-08.json`](../catalog/coverage/2026-08.json) 仍誠實固定在 8/23。全站 80 個 logical periods 的 latest canonical records 為 7,979 筆；其中 78 個 August monthly periods 為 7,962 筆，另兩個既有 non-month periods 合計 17 筆。

## 1. 權威集合與完成判準

August registry 的唯一分母是 [`catalog/journals.json`](../catalog/journals.json) 中的 **65 本期刊**。Cambridge provider catalog 是額外 discovery surface，不回頭改寫這個分母。

[`catalog/coverage/2026-08.json`](../catalog/coverage/2026-08.json) 已為 65/65 本留下 terminal outcome：

| Outcome | 期刊數 |
|---|---:|
| `PUBLISHED` | 61 |
| `NO_MATCHING_ARTICLES` | 3 |
| `OUTSIDE_WINDOW` | 1 |
| `DATE_EVIDENCE_INSUFFICIENT` | 0 |
| **合計** | **65** |

61 本 canonical August MTD editions 合計 **6,339 筆 article records**；4 本沒有 publication 的期刊均以明確 terminal status 保存，沒有用 fabricated empty edition 假裝成功。

Coverage regression test 會檢查 row-level 與 aggregate-level 計數一致，並要求最新 coverage ledger 完整覆蓋當前 registry；歷史月份則保留當時的 registry 分母，不會被未來新增期刊回寫。

## 2. 新增 OA 期刊與 terminal outcomes

本次加入 7 本 fully-OA 期刊：American Journal of Men's Health、BMC Psychology、BMC Women's Health、Journal of Family Research、Reproductive Health、Sexual and Reproductive Health Matters、Sexual Medicine。前五個有 August records 的期刊已發布 canonical r01 editions，BMC 兩刊以 `TRIAGE` 處理大量 metadata；另外兩刊保留可稽核的 no-edition outcome。

Frontiers in Psychology 的 Gender, Sex and Sexualities section 沒有以整本期刊加入。現有 acquisition contract 尚無 section-level filter，整刊收錄會把無關文章混入；待 section identity/filter 可驗證後再納入。

### 沒有 publication 的四個 terminal outcomes

| 期刊 | Outcome | 依據 |
|---|---|---|
| American Journal of Men's Health | `NO_MATCHING_ARTICLES` | Crossref、PubMed、Europe PMC 在 2026-08-01..23 都沒有匹配 publication record。 |
| Journal of Machine Learning Research | `NO_MATCHING_ARTICLES` | Official JMLR RSS 仍只有 year-level `pubDate`，沒有可歸入 August 的日／月證據。 |
| Sexual Medicine | `NO_MATCHING_ARTICLES` | Exact-ISSN Crossref 為零；PubMed／Europe PMC 當前結果的 DOI/container 實屬另一份非 fully-OA 的 *The Journal of Sexual Medicine*，因此 fail closed 排除。 |
| Transactions of the Association for Computational Linguistics | `OUTSIDE_WINDOW` | ACL Anthology candidates 的可核對 Crossref 日／月出版日期仍不在 8/1..23。 |

### 先前缺口的 targeted repair

Information Processing & Management、Journal of Sport and Health Science、Natural Language Processing Journal 與 Psychology of Sport and Exercise 各有 1 筆新近可核實的 August month-precision record，已分別建立 r01。Psychology of Sport and Exercise 的 PubMed year-only candidates 沒有被強行歸入 August。

### Chemical Science repair

Chemical Science 原本的 date-evidence gap 已關閉並發布 76 筆 scholarly records。這不是放寬成「Crossref created date 一律可用」：只接受 journal-specific 的 RSC `First published` surrogate，且先以 21/21 official RSC controls 驗證 day-level exact match；83 個 in-window candidates 中另排除 7 個 cover/contents records。Generic Crossref created dates 仍禁止當作 publication-date evidence。

## 3. August corpus 與 provider extension

8/29 publication refresh 後的 repository snapshot：

- Authoritative registry：65 個 slugs；其中 61 個既有 August MTD publications 已延伸至 8/29，共 **7,891 筆 records**；terminal-coverage ledger 仍固定至 8/23。
- Selected Cambridge provider additions：17 個 August MTD publications 已延伸至 8/29，共 **71 筆 records**，不改變 65 本 registry 的完成分母。
- 全站包含 **78 個 journal slugs、80 periods、297 revisions、7,979 筆 latest canonical records**。
- 下節的 3,796 筆 Pages projection 與 evidence funnel 是 8/23 baseline，未被這次 metadata suffix refresh 倒灌改寫。

Cambridge provider catalog 當時列出 200 本 fully-OA journals，但 catalog presence 不等於已生成 edition。只有經 live request 選中的 journal 才進 canonical store。

## 4. 跨刊 evidence-processing funnel

本次 snapshot 的本機 exact-source complete-edition dry run 顯示：

| 階段 | 結果 |
|---|---:|
| Canonical records | 6,415 |
| Abstract fetch plan | 300 |
| Abstract acquired / absent | 209 / 91 |
| Full-text-now allocation | 120 |
| Full text acquired / access denied / route not found | 16 / 53 / 51 |
| Evidence-reporting evaluation completed | 7 |
| Limited: no machine-readable text | 9 |
| Editorial featured / reserve / limited review | 7 / 0 / 113 |

Raw abstract/full-text payloads 在 structural review 與 digest verification 後、artifact upload 前刪除，沒有寫入 Git 或發布到 Pages。`access denied` 與 `route not found` 被保留為可稽核結果，沒有改寫成已取得全文。

本輪 7 筆 featured items 只代表取得 machine-readable evidence text 並通過 reporting evaluation 的 bounded subset；不代表其研究結論比其他文章更可信。

| Primary path | 數量 |
|---|---:|
| Evaluated binding SHA-256 | `2d97f211cf5b7b23a211d9e1c028197bd42100b7baf7d3f40e1801be90dc6ee8` |

這個 funnel 衡量的是可取得性、研究設計線索與 reporting coverage，**不是研究品質排行榜**。本輪沒有完成 risk-of-bias assessment，也沒有評估 effect magnitude；`FEATURED` 不等於結論可信、效應成立或可直接採用。

## 5. 跨刊 synthesis

### 臨床介入與 implementation 是 featured trial 的主軸

Randomized-trial cluster 涵蓋心臟手術後止痛、把高血壓照護整合進 HIV services、失智照顧者的網路自助 ACT、time-restricted eating 的 12 個月追蹤、腹膜透析感染訓練、精神疾病 self-stigma peer programme，以及失眠 CBT 與 epigenetic ageing。共同問題不是單一療法誰「贏」，而是 intervention 在多中心、長期追蹤或 routine-care implementation 下是否仍站得住。

### Safety、營養、老化與復健形成另一條密集線

Prospective / safety items 集中在 plant-based diet 與 ultra-processed food、malnutrition / frailty 與術後死亡、嚴重瘧疾合併 AKI 的長期風險、coeliac disease、dengue vaccine pharmacovigilance、90 歲後 dementia incidence，以及 Achilles tendon rupture、hip fracture gait recovery 等。這一群多為 cohort evidence，適合追蹤風險與 trajectory，但不能被寫成 randomized causal effect。

### 驗證與 evidence infrastructure 不只是「又一個模型」

Validation / synthesis cluster 包括 CKD chest-radiograph deep learning、glaucoma progression、wrist PPG cardiac-arrest detection、respiratory early-warning system，以及 infection、frailty、HBV/HIV、radiotherapy biomarkers 等 systematic reviews。Journal of Clinical Epidemiology 的 items 也直接指向 external-validation reporting 與 estimand / conclusion discrepancy。跨刊訊號是：模型或 pooled estimate 的 headline 之外，external validation、reporting completeness、data availability 與 transportability 才是能否進入下一步 evidence work 的瓶頸。

以上 synthesis 是 2026-08-14 snapshot 的歷史解讀，沒有自動外推到新增的關係、性別與性健康期刊。本次更新的 evidence funnel 是 6,415 筆 corpus 中 bounded 300-item plan 的可取得性稽核，不能反推為整體 corpus 的主題盛行率。

## 6. Production verification

本次更新在 merge 前完成 140 項測試、canonical bundle 驗證、Pages build 與 complete-edition dry run。merge 後以 exact merge SHA 核對 CI、Pages workflow、live `links.json`、coverage ledger、journal HTML 與 immutable revision URL；run IDs 與 deployed checksum 以 GitHub Actions / Pages live readback 為準。

2026-08-29 refresh 以九份 backfill receipts 覆蓋 78 本既有 August publications。每批均完成 live suffix acquisition、canonical validation、guarded PR publication 與 exact-SHA Pages／evidence lane；最後 canonical main SHA 為 `4c9d2bd83ff9c1973711292dd8ba5362216dcf0d`，terminal Pages run 為 [`33239973141`](https://github.com/hoiyu915-droid/EvidenceRadar-Editions/actions/runs/33239973141)。Scientific Reports 首次以 1,000-record cap 執行時因 Crossref 回報 1,619 筆而正確 fail closed；cap 僅對該刊提高至 bounded 2,000 後才重新發布，沒有 partial publication。

前一個 2026-08-14 production baseline 保留如下，供 history compatibility 核對：

- Live scoped edition run [`31934105615`](https://github.com/hoiyu915-droid/EvidenceRadar-Editions/actions/runs/31934105615) 成功完成 build、validate、canonical publish、merge、Pages dispatch 與 exact-SHA wait；Memory, Mind & Media r01 發布 2 筆 records。
- Pages / downstream evidence run [`31934127582`](https://github.com/hoiyu915-droid/EvidenceRadar-Editions/actions/runs/31934127582) 在 SHA `6b09654c4e171128f1e52f430cb26c725b7caf79` 全步驟成功。
- Complete-edition artifact digest：`sha256:57d2a6fc48ffa659cb73ff2e4dcfc4b2d62585b63567270d82d1fe9d4ed0fb09`。
- GitHub Pages artifact digest：`sha256:b69300b74fd952e1c6dc21f9abee98c53a4f9c506491664213a562c76cff2d6a`。
- Public portal：<https://hoiyu915-droid.github.io/EvidenceRadar-Editions/>。

## 7. 後續月份語義

這個 closeout 的 authoritative registry terminal-coverage ledger 固定在 **2026-08 MTD through 2026-08-23**；2026-08-29 另完成一次針對全部 78 個既有 canonical bases 的明示 suffix refresh。兩者不能混寫：前者包含四個 no-edition outcomes，後者只延伸已存在的 publications。2026-08-31 結束後若要發布完整月份，必須以新 revision 建立 `FINAL`，重新 probe 全部 registry outcomes，並重建 coverage ledger、跨刊 synthesis 與 production verification。
