import copy
import unittest

from evidenceradar_editions.editorial_shortlist import (
    build_editorial_shortlist,
    builtin_editorial_shortlist_policy,
)


def record(
    index: int,
    *,
    journal: str = "Journal A",
    journal_slug: str = "journal-a",
    path: str = "EVIDENCE_SYNTHESIS",
    route: str = "FETCH_CANDIDATE",
    category: str = "clinical_medicine",
    title: str | None = None,
    processing_mode: str = "FULL",
    integrity: bool = False,
):
    canonical_id = f"doi:10.1000/{journal_slug}.{index}"
    return {
        "canonical_id": canonical_id,
        "journal": journal,
        "journal_slug": journal_slug,
        "period_key": "2026-08",
        "revision": 1,
        "publication_date": "2026-08-13",
        "publication_date_precision": "DAY",
        "title_original": title or f"{path} article {index} about topic {index}",
        "title_zh_tw": f"測試文章 {index}",
        "article_type": "journal-article",
        "authors": ["A Author"],
        "identifiers": {
            "doi": canonical_id.removeprefix("doi:"),
            "pmid": str(100000 + index),
            "pmcid": None,
        },
        "source_urls": [f"https://doi.org/{canonical_id.removeprefix('doi:')}"],
        "categories": [category],
        "publication_role": "concern" if integrity else "primary",
        "matched_paths": [path],
        "primary_path": path,
        "score": 94 if route == "FETCH_CANDIDATE" else 72,
        "raw_score": 94 if route == "FETCH_CANDIDATE" else 72,
        "reason_codes": [path, "PMID_ROUTE", "DOI_ROUTE"],
        "route": "INTEGRITY_REVIEW" if integrity else route,
        "processing_mode": processing_mode,
        "processing_policy_source": "test",
        "journal_soft_cap_demoted": False,
        "full_text_fetched": False,
        "abstract_reviewed": False,
        "evidence_evaluated": False,
        "edition_url": f"journals/{journal_slug}/2026-08/r01/",
        "canonical_json_url": f"journals/{journal_slug}/2026-08/r01/edition.json",
    }


def audit(journal_slug: str, articles):
    return {
        "artifact_type": "EvidenceRadar_Editions_PrefetchTriageAudit",
        "journal": journal_slug.replace("-", " ").title(),
        "journal_slug": journal_slug,
        "period_key": "2026-08",
        "revision": 1,
        "articles": list(articles),
    }


def small_policy(*, fetch_target=6, hold_target=12):
    policy = builtin_editorial_shortlist_policy()
    policy["fetch_now_target"] = fetch_target
    policy["hold_reserve_target"] = hold_target
    policy["category_minimums"] = {}
    policy["category_soft_caps"] = {
        key: fetch_target for key in policy["category_order"]
    }
    policy["category_hard_caps"] = {
        key: fetch_target for key in policy["category_order"]
    }
    policy["path_minimums"] = {
        key: 0 for key in policy["path_order"]
    }
    policy["path_soft_caps"] = {
        key: fetch_target for key in policy["path_order"]
    }
    policy["path_hard_caps"] = {
        key: fetch_target for key in policy["path_order"]
    }
    policy["journal_fetch_caps"] = {
        "FULL": 2,
        "TRIAGE": 3,
        "INDEX_ONLY": 1,
        "SUSPENDED": 0,
    }
    policy["journal_hold_caps"] = {
        "FULL": 6,
        "TRIAGE": 8,
        "INDEX_ONLY": 2,
        "SUSPENDED": 0,
    }
    return policy


class EditorialShortlistTests(unittest.TestCase):
    def test_bounded_fetch_plan_balances_journals_and_audits_every_record(self):
        audits = []
        paths = [
            "GUIDANCE",
            "EVIDENCE_SYNTHESIS",
            "RANDOMIZED_TRIAL",
            "REPLICATION_VALIDATION",
            "SAFETY_SIGNAL",
            "RESOURCE_BENCHMARK",
        ]
        total = 0
        for journal_index in range(4):
            slug = f"journal-{journal_index}"
            articles = []
            for index in range(8):
                articles.append(
                    record(
                        index + journal_index * 100,
                        journal_slug=slug,
                        journal=f"Journal {journal_index}",
                        path=paths[index % len(paths)],
                        category=(
                            "clinical_medicine"
                            if journal_index % 2 == 0
                            else "llm_research"
                        ),
                    )
                )
            audits.append(audit(slug, articles))
            total += len(articles)

        shortlist, edition_audits = build_editorial_shortlist(
            audits,
            policy=small_policy(fetch_target=6, hold_target=12),
            generated_at="2026-08-15T00:00:00Z",
        )
        self.assertEqual(shortlist["counts"]["canonical_article_count"], total)
        self.assertEqual(shortlist["counts"]["fetch_now_count"], 6)
        self.assertEqual(shortlist["counts"]["hold_reserve_count"], 12)
        self.assertEqual(
            shortlist["abstract_fetch_plan"]["item_count"],
            shortlist["counts"]["fetch_now_count"],
        )
        self.assertEqual(
            sum(len(value["articles"]) for value in edition_audits.values()),
            total,
        )
        journal_counts = shortlist["fetch_now_journal_counts"]
        self.assertTrue(all(value <= 2 for value in journal_counts.values()))
        self.assertGreaterEqual(len(journal_counts), 3)
        self.assertTrue(
            all(
                item["abstract_fetch_requested"] is False
                and item["abstract_acquired"] is False
                and item["abstract_reviewed"] is False
                for item in shortlist["abstract_fetch_plan"]["items"]
            )
        )

    def test_near_duplicate_does_not_crowd_out_another_path(self):
        articles = [
            record(
                1,
                title="Systematic review of protein intake and muscle mass in older adults",
                path="EVIDENCE_SYNTHESIS",
            ),
            record(
                2,
                title="A systematic review of protein intake and muscle mass among older adults",
                path="EVIDENCE_SYNTHESIS",
            ),
            record(
                3,
                title="Randomized controlled trial of balance training after stroke",
                path="RANDOMIZED_TRIAL",
            ),
        ]
        policy = small_policy(fetch_target=2, hold_target=2)
        shortlist, _ = build_editorial_shortlist(
            [audit("journal-a", articles)],
            policy=policy,
            generated_at="2026-08-15T00:00:00Z",
        )
        fetch = [
            item
            for item in shortlist["items"]
            if item["editorial_route"] == "FETCH_NOW"
        ]
        self.assertEqual(len(fetch), 2)
        self.assertEqual(
            {item["primary_path"] for item in fetch},
            {"EVIDENCE_SYNTHESIS", "RANDOMIZED_TRIAL"},
        )
        hold = [
            item
            for item in shortlist["items"]
            if item["editorial_route"] == "HOLD_RESERVE"
        ]
        self.assertTrue(
            any("NEAR_DUPLICATE_TITLE" in item["decision_reasons"] for item in hold)
        )

    def test_integrity_attention_never_consumes_abstract_fetch_slot(self):
        articles = [
            record(
                1,
                path="INTEGRITY_EVENT",
                integrity=True,
                title="Retraction Note: Example article",
            ),
            record(
                2,
                path="RANDOMIZED_TRIAL",
                title="Randomized controlled trial of intervention X",
            ),
        ]
        shortlist, _ = build_editorial_shortlist(
            [audit("journal-a", articles)],
            policy=small_policy(fetch_target=1, hold_target=1),
            generated_at="2026-08-15T00:00:00Z",
        )
        self.assertEqual(shortlist["counts"]["integrity_attention_count"], 1)
        plan_keys = {
            item["record_key"]
            for item in shortlist["abstract_fetch_plan"]["items"]
        }
        integrity = [
            item
            for item in shortlist["items"]
            if item["integrity_attention"]
        ][0]
        self.assertEqual(integrity["editorial_route"], "CATALOG_ONLY")
        self.assertNotIn(integrity["record_key"], plan_keys)
        self.assertEqual(integrity["integrity_action"], "RECORD_MAINTENANCE")

    def test_reserve_backfill_is_explicit(self):
        articles = [
            record(1, path="EVIDENCE_SYNTHESIS", route="FETCH_CANDIDATE"),
            record(2, path="OBSERVATIONAL_DESIGN", route="RESERVE"),
        ]
        policy = small_policy(fetch_target=2, hold_target=2)
        policy["journal_fetch_caps"]["FULL"] = 2
        shortlist, _ = build_editorial_shortlist(
            [audit("journal-a", articles)],
            policy=policy,
            generated_at="2026-08-15T00:00:00Z",
        )
        fetch = [
            item
            for item in shortlist["items"]
            if item["editorial_route"] == "FETCH_NOW"
        ]
        self.assertEqual(len(fetch), 2)
        self.assertTrue(
            any(
                "PREFETCH_RESERVE_BACKFILL" in item["decision_reasons"]
                for item in fetch
            )
        )

    def test_bindings_are_deterministic_and_tamper_sensitive(self):
        audits = [
            audit(
                "journal-a",
                [
                    record(1, path="EVIDENCE_SYNTHESIS"),
                    record(2, path="RANDOMIZED_TRIAL"),
                ],
            )
        ]
        policy = small_policy(fetch_target=2, hold_target=2)
        first, _ = build_editorial_shortlist(
            audits,
            policy=policy,
            generated_at="2026-08-15T00:00:00Z",
        )
        second, _ = build_editorial_shortlist(
            audits,
            policy=policy,
            generated_at="2030-01-01T00:00:00Z",
        )
        self.assertEqual(
            first["shortlist_binding_sha256"],
            second["shortlist_binding_sha256"],
        )
        self.assertEqual(
            first["abstract_fetch_plan"]["plan_binding_sha256"],
            second["abstract_fetch_plan"]["plan_binding_sha256"],
        )

        changed = copy.deepcopy(audits)
        changed[0]["articles"][0]["score"] -= 1
        tampered, _ = build_editorial_shortlist(
            changed,
            policy=policy,
            generated_at="2026-08-15T00:00:00Z",
        )
        self.assertNotEqual(
            first["shortlist_binding_sha256"],
            tampered["shortlist_binding_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
