# 2026 年 8 月 Editions 完成紀錄

**狀態：August MTD coverage complete（資料窗口至 2026-08-14 UTC）**

這份紀錄封存 2026 年 8 月的 authoritative registry coverage、例外處理、跨刊篩選結果與 production 驗證。它不是 8 月 `FINAL`：完整月份只能在 2026-08-31 結束後以新 revision 重建，不能覆寫既有 MTD publication。

## 1. 權威集合與完成判準

August registry 的唯一分母是 [`catalog/journals.json`](../catalog/journals.json) 中的 **58 本期刊**。Cambridge provider catalog 是額外 discovery surface，不回頭改寫這個分母。

[`catalog/coverage/2026-08.json`](../catalog/coverage/2026-08.json) 已為 58/58 本留下 terminal outcome：

| Outcome | 期刊數 |
|---|---:|
| `PUBLISHED` | 52 |
| `NO_MATCHING_ARTICLES` | 4 |
| `OUTSIDE_WINDOW` | 2 |
| `DATE_EVIDENCE_INSUFFICIENT` | 0 |
| **合計** | **58** |

52 本 canonical August MTD editions 合計 **4,389 筆 article records**；6 本沒有 publication 的期刊均以明確 terminal status 保存，沒有用 fabricated empty edition 假裝成功。

本次 closeout 同時修正一個 stale aggregate：Chemical Science 的 journal row 已是 `PUBLISHED`，但檔尾一度仍寫成 51 published、1 date-evidence gap、7 no-edition。現在 row-level 與 aggregate-level 都是 52 / 0 / 6，並加入 regression test，之後任何 coverage JSON 的彙總數若與 journal rows 不一致，CI 會直接失敗。

## 2. 沒有 publication 的六個 terminal outcomes

| 期刊 | Outcome | 依據 |
|---|---|---|
| Information Processing & Management | `NO_MATCHING_ARTICLES` | Exact-ISSN Crossref publication-date reconstruction 在 2026-08-01..14 為零。 |
| Journal of Machine Learning Research | `NO_MATCHING_ARTICLES` | Official JMLR RSS 在窗口內沒有 `pubDate`。 |
| Journal of Sport and Health Science | `NO_MATCHING_ARTICLES` | Crossref、PubMed、Europe PMC 都沒有匹配 publication record。 |
| Natural Language Processing Journal | `NO_MATCHING_ARTICLES` | Exact-ISSN Crossref 沒有 publication-date record；created date 未被冒充 publication date。 |
| Psychology of Sport and Exercise | `OUTSIDE_WINDOW` | 3 個 PubMed YEAR-only candidates 經 DOI 核對後，Crossref published/issued dates 都是 2026 年 11 月。 |
| Transactions of the Association for Computational Linguistics | `OUTSIDE_WINDOW` | ACL Anthology 找到 34 個 2026-volume candidates；34 個可核對的 Crossref DAY/MONTH dates 均不在 8/1..14。 |

### Chemical Science repair

Chemical Science 原本的 date-evidence gap 已關閉並發布 76 筆 scholarly records。這不是放寬成「Crossref created date 一律可用」：只接受 journal-specific 的 RSC `First published` surrogate，且先以 21/21 official RSC controls 驗證 day-level exact match；83 個 in-window candidates 中另排除 7 個 cover/contents records。Generic Crossref created dates 仍禁止當作 publication-date evidence。

## 3. August corpus 與 provider extension

在 exact production SHA `6b09654c4e171128f1e52f430cb26c725b7caf79` 上：

- 2026-08 最新 editions：**61 個 journal slugs、4,398 筆 records**。
- 其中 authoritative registry：52 個 slugs、4,389 筆 records。
- Selected Cambridge additions：9 個 slugs、9 筆 records；它們是補充 publication，不改變 58 本 registry 的完成分母。
- 全站另保留 JAMA Network Open 的 2026-08-13 與 2026-08-14 兩個 day periods，共 17 筆；因此全 corpus 為 **61 journal slugs、63 periods、64 revisions、4,415 canonical records**。

Cambridge provider catalog 當時列出 200 本 fully-OA journals，但 catalog presence 不等於已生成 edition。只有經 live request 選中的 journal 才進 canonical store。

## 4. 跨刊 evidence-processing funnel

Pages run `31934127582` 產生的 exact-SHA complete-edition artifact 顯示：

| 階段 | 結果 |
|---|---:|
| Canonical records | 4,415 |
| Abstract fetch plan | 300 |
| Abstract acquired / absent | 205 / 95 |
| Full-text-now allocation | 120 |
| Full text acquired / route not found | 69 / 51 |
| Evidence-reporting evaluation completed | 62 |
| Limited: no machine-readable text | 7 |
| Editorial featured / reserve / limited review | 36 / 26 / 58 |

69 份全文中，61 份來自 Crossref open TDM links，8 份來自 Europe PMC XML；本輪沒有 access-denied 或 acquisition-inconclusive outcome。Raw abstract/full-text payloads 在 structural review 與 digest verification 後、artifact upload 前刪除，沒有寫入 Git 或發布到 Pages。

36 筆 featured items 的 primary-path 分布為：

| Primary path | 數量 |
|---|---:|
| Randomized trial | 7 |
| Safety signal | 7 |
| Observational design | 7 |
| Evidence synthesis | 6 |
| Prospective longitudinal | 5 |
| Replication / validation | 3 |
| Survey | 1 |

這個 funnel 衡量的是可取得性、研究設計線索與 reporting coverage，**不是研究品質排行榜**。本輪沒有完成 risk-of-bias assessment，也沒有評估 effect magnitude；`FEATURED` 不等於結論可信、效應成立或可直接採用。

## 5. 跨刊 synthesis

### 臨床介入與 implementation 是 featured trial 的主軸

Randomized-trial cluster 涵蓋心臟手術後止痛、把高血壓照護整合進 HIV services、失智照顧者的網路自助 ACT、time-restricted eating 的 12 個月追蹤、腹膜透析感染訓練、精神疾病 self-stigma peer programme，以及失眠 CBT 與 epigenetic ageing。共同問題不是單一療法誰「贏」，而是 intervention 在多中心、長期追蹤或 routine-care implementation 下是否仍站得住。

### Safety、營養、老化與復健形成另一條密集線

Prospective / safety items 集中在 plant-based diet 與 ultra-processed food、malnutrition / frailty 與術後死亡、嚴重瘧疾合併 AKI 的長期風險、coeliac disease、dengue vaccine pharmacovigilance、90 歲後 dementia incidence，以及 Achilles tendon rupture、hip fracture gait recovery 等。這一群多為 cohort evidence，適合追蹤風險與 trajectory，但不能被寫成 randomized causal effect。

### 驗證與 evidence infrastructure 不只是「又一個模型」

Validation / synthesis cluster 包括 CKD chest-radiograph deep learning、glaucoma progression、wrist PPG cardiac-arrest detection、respiratory early-warning system，以及 infection、frailty、HBV/HIV、radiotherapy biomarkers 等 systematic reviews。Journal of Clinical Epidemiology 的 items 也直接指向 external-validation reporting 與 estimand / conclusion discrepancy。跨刊訊號是：模型或 pooled estimate 的 headline 之外，external validation、reporting completeness、data availability 與 transportability 才是能否進入下一步 evidence work 的瓶頸。

以上 synthesis 來自被 pipeline 選入並取得 abstract/full text 的 300/205/69 筆子集合，會偏向 identifier 完整、open-text route 可用及 clinical reporting 結構較清楚的期刊；不能反推為 4,415 筆 corpus 的主題盛行率。

## 6. Production verification

- Live scoped edition run [`31934105615`](https://github.com/hoiyu915-droid/EvidenceRadar-Editions/actions/runs/31934105615) 成功完成 build、validate、canonical publish、merge、Pages dispatch 與 exact-SHA wait；Memory, Mind & Media r01 發布 2 筆 records。
- Pages / downstream evidence run [`31934127582`](https://github.com/hoiyu915-droid/EvidenceRadar-Editions/actions/runs/31934127582) 在 SHA `6b09654c4e171128f1e52f430cb26c725b7caf79` 全步驟成功。
- Complete-edition artifact digest：`sha256:57d2a6fc48ffa659cb73ff2e4dcfc4b2d62585b63567270d82d1fe9d4ed0fb09`。
- GitHub Pages artifact digest：`sha256:b69300b74fd952e1c6dc21f9abee98c53a4f9c506491664213a562c76cff2d6a`。
- Public portal：<https://hoiyu915-droid.github.io/EvidenceRadar-Editions/>。

## 7. 後續月份語義

這個 closeout 固定的是 **2026-08 MTD through 2026-08-14** 的 registry completion。8/14 之後不因「更新鮮」而把 58 本全部重跑成無意義的 r02；只對 failed、partial、missing 或經證據確認需要 repair 的 journal 做 targeted rerun。2026-08-31 結束後若要發布完整月份，必須以新 revision 建立 `FINAL`，並重新產生 coverage ledger、跨刊 synthesis 與 production verification。
