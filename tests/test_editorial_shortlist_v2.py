import copy
import unittest

from evidenceradar_editions.editorial_shortlist_v2 import (
    build_editorial_shortlist_v2,
    builtin_editorial_shortlist_policy_v2,
)


def record(
    index: int,
    *,
    journal_slug: str,
    journal: str | None = None,
    route: str = "RESERVE",
    path: str = "EVIDENCE_SYNTHESIS",
    processing_mode: str = "FULL",
    with_identifier: bool = True,
):
    doi = f"10.1000/{journal_slug}.{index}" if with_identifier else None
    return {
        "canonical_id": f"doi:{doi}" if doi else f"title:{journal_slug}.{index}",
        "journal": journal or journal_slug.replace("-", " ").title(),
        "journal_slug": journal_slug,
        "period_key": "2026-08",
        "revision": 1,
        "publication_date": f"2026-08-{(index % 27) + 1:02d}",
        "publication_date_precision": "DAY",
        "title_original": f"{path} distinct topic marker {journal_slug} token{index}",
        "title_zh_tw": f"測試文章 {index}",
        "article_type": "journal-article",
        "authors": ["A Author"],
        "identifiers": {"doi": doi, "pmid": None, "pmcid": None},
        "source_urls": [f"https://doi.org/{doi}"] if doi else [],
        "categories": ["field"],
        "publication_role": "primary",
        "matched_paths": [path],
        "primary_path": path,
        "score": 90 if route == "FETCH_CANDIDATE" else 70,
        "raw_score": 90 if route == "FETCH_CANDIDATE" else 70,
        "reason_codes": [path, "DOI_ROUTE"] if doi else [path],
        "route": route,
        "processing_mode": processing_mode,
        "processing_policy_source": "test",
        "journal_soft_cap_demoted": False,
        "full_text_fetched": False,
        "abstract_reviewed": False,
        "evidence_evaluated": False,
        "edition_url": f"journals/{journal_slug}/2026-08/r01/",
        "canonical_json_url": f"journals/{journal_slug}/2026-08/r01/edition.json",
    }


def audit(slug: str, articles):
    return {
        "artifact_type": "EvidenceRadar_Editions_PrefetchTriageAudit",
        "journal": slug.replace("-", " ").title(),
        "journal_slug": slug,
        "period_key": "2026-08",
        "revision": 1,
        "articles": list(articles),
    }


def impact_registry(values, *, unknown=()):
    journals = {}
    for slug, value in values.items():
        journals[slug] = {
            "name": slug,
            "publisher": "Publisher",
            "categories": ["field"],
            "status": "VERIFIED_PUBLISHER_DISPLAY",
            "metrics": {"JIF": {"value": value, "year": 2025}},
            "source_url": f"https://example.test/{slug}",
            "source_note": "test",
        }
    for slug in unknown:
        journals[slug] = {
            "name": slug,
            "publisher": "Publisher",
            "categories": ["field"],
            "status": "NO_PUBLIC_VERIFIED_METRIC",
            "metrics": {},
            "source_url": f"https://example.test/{slug}",
            "source_note": "neutral",
        }
    return {
        "schema_version": "1.0",
        "artifact_type": "EvidenceRadar_Editions_JournalImpactRegistry",
        "observed_at": "2026-08-15",
        "semantics": "test",
        "metric_preference": ["JIF", "CITESCORE"],
        "normalization": {
            "peer_group": "registry_category_and_metric_kind",
            "percentile_method": "midrank",
            "multi_category_aggregation": "arithmetic_mean",
            "unknown_percentile": 50.0,
        },
        "journals": journals,
    }


def policy(target: int):
    value = builtin_editorial_shortlist_policy_v2()
    value["fetch_now_target"] = target
    value["journal_fetch_caps"] = {
        "FULL": 100,
        "TRIAGE": 100,
        "INDEX_ONLY": 20,
        "SUSPENDED": 0,
    }
    value["topic_soft_caps_by_mode"] = {
        "FULL": 100,
        "TRIAGE": 100,
        "INDEX_ONLY": 20,
        "SUSPENDED": 0,
    }
    value["topic_hard_caps_by_mode"] = copy.deepcopy(
        value["topic_soft_caps_by_mode"]
    )
    value["near_duplicate_jaccard_threshold"] = 1.0
    return value


class EditorialShortlistV2Tests(unittest.TestCase):
    def test_metric_independent_candidate_precedes_high_metric_reserve(self):
        audits = [
            audit("low", [record(1, journal_slug="low", route="FETCH_CANDIDATE")]),
            audit("high", [record(2, journal_slug="high", route="RESERVE")]),
        ]
        result, _ = build_editorial_shortlist_v2(
            audits,
            policy=policy(1),
            impact_registry=impact_registry({"low": 1.0, "high": 20.0}),
            generated_at="2026-08-15T00:00:00Z",
        )
        selected = [
            item for item in result["items"] if item["editorial_route"] == "FETCH_NOW"
        ]
        self.assertEqual([item["journal_slug"] for item in selected], ["low"])
        self.assertIn(
            "METRIC_INDEPENDENT_PREFETCH_CANDIDATE",
            selected[0]["decision_reasons"],
        )

    def test_impact_prior_changes_reserve_capture(self):
        audits = [
            audit(
                "high",
                [record(i, journal_slug="high", route="RESERVE") for i in range(10)],
            ),
            audit(
                "low",
                [record(100 + i, journal_slug="low", route="RESERVE") for i in range(10)],
            ),
        ]
        p = policy(12)
        p["capture_bands"] = [
            {"minimum_percentile": 75, "capture_rate": 1.0, "label": "HIGH"},
            {"minimum_percentile": 0, "capture_rate": 0.2, "label": "LOW"},
        ]
        result, _ = build_editorial_shortlist_v2(
            audits,
            policy=p,
            impact_registry=impact_registry({"high": 20.0, "low": 1.0}),
            generated_at="2026-08-15T00:00:00Z",
        )
        counts = result["fetch_now_journal_counts"]
        self.assertEqual(counts["high"], 10)
        self.assertEqual(counts["low"], 2)

    def test_processing_mode_damps_high_volume_journal(self):
        audits = [
            audit(
                "full",
                [record(i, journal_slug="full", processing_mode="FULL") for i in range(20)],
            ),
            audit(
                "triage",
                [
                    record(100 + i, journal_slug="triage", processing_mode="TRIAGE")
                    for i in range(20)
                ],
            ),
        ]
        p = policy(24)
        p["capture_bands"] = [
            {"minimum_percentile": 0, "capture_rate": 0.8, "label": "ALL"}
        ]
        p["mode_capture_modifiers"]["FULL"] = 1.0
        p["mode_capture_modifiers"]["TRIAGE"] = 0.5
        result, _ = build_editorial_shortlist_v2(
            audits,
            policy=p,
            impact_registry=impact_registry({"full": 5.0, "triage": 5.0}),
            generated_at="2026-08-15T00:00:00Z",
        )
        self.assertEqual(result["fetch_now_journal_counts"]["full"], 16)
        self.assertEqual(result["fetch_now_journal_counts"]["triage"], 8)

    def test_global_ceiling_is_hard_and_candidates_round_robin(self):
        audits = []
        for j in range(4):
            slug = f"journal-{j}"
            audits.append(
                audit(
                    slug,
                    [
                        record(
                            j * 1000 + i,
                            journal_slug=slug,
                            route="FETCH_CANDIDATE",
                        )
                        for i in range(100)
                    ],
                )
            )
        result, editions = build_editorial_shortlist_v2(
            audits,
            policy=policy(30),
            impact_registry=impact_registry(
                {f"journal-{j}": float(j + 1) for j in range(4)}
            ),
            generated_at="2026-08-15T00:00:00Z",
        )
        self.assertEqual(result["counts"]["fetch_now_count"], 30)
        counts = result["fetch_now_journal_counts"]
        self.assertEqual(sum(counts.values()), 30)
        self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)
        self.assertEqual(
            sum(len(value["articles"]) for value in editions.values()),
            400,
        )

    def test_missing_metric_is_neutral_and_all_states_remain_false(self):
        audits = [
            audit(
                "unknown",
                [record(i, journal_slug="unknown") for i in range(4)],
            )
        ]
        result, editions = build_editorial_shortlist_v2(
            audits,
            policy=policy(4),
            impact_registry=impact_registry({}, unknown=("unknown",)),
            generated_at="2026-08-15T00:00:00Z",
        )
        summary = result["journal_summaries"][0]
        self.assertTrue(summary["impact_prior"]["unknown_metric"])
        self.assertEqual(
            summary["impact_prior"]["registry_category_percentile"], 50.0
        )
        all_records = [
            item for audit_value in editions.values() for item in audit_value["articles"]
        ]
        self.assertTrue(
            all(
                item["abstract_fetch_requested"] is False
                and item["abstract_acquired"] is False
                and item["abstract_reviewed"] is False
                and item["full_text_fetched"] is False
                and item["evidence_evaluated"] is False
                for item in all_records
            )
        )

    def test_impact_registry_is_bound_into_shortlist_and_plan(self):
        audits = [audit("journal", [record(1, journal_slug="journal")])]
        p = policy(1)
        first, _ = build_editorial_shortlist_v2(
            audits,
            policy=p,
            impact_registry=impact_registry({"journal": 5.0}),
            generated_at="2026-08-15T00:00:00Z",
        )
        changed, _ = build_editorial_shortlist_v2(
            audits,
            policy=p,
            impact_registry=impact_registry({"journal": 5.1}),
            generated_at="2026-08-15T00:00:00Z",
        )
        self.assertNotEqual(
            first["impact_registry_sha256"], changed["impact_registry_sha256"]
        )
        self.assertNotEqual(
            first["shortlist_binding_sha256"],
            changed["shortlist_binding_sha256"],
        )
        self.assertNotEqual(
            first["abstract_fetch_plan"]["plan_binding_sha256"],
            changed["abstract_fetch_plan"]["plan_binding_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
