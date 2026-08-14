from __future__ import annotations

import json
from pathlib import Path

UPSTREAM = {
    "repository": "hoiyu915-droid/EvidenceRadar",
    "commit": "6da659df845e4b76072dae016120ca76ed9c27c4",
    "config": "config/radar_master.json",
    "config_blob_sha": "ea8e6dcd8246187e7e87e580087e62a02b9fb870",
    "configured_sources": 83,
    "active_sources": 59,
    "planned_sources": 24,
}
CATEGORY_LABELS = {
    "clinical_medicine": "臨床醫學",
    "sport_science": "運動科學",
    "sport_nutrition_fitness": "運動營養／體適能",
    "llm_research": "AI／LLM",
    "human_ai": "Human-AI／HCI",
    "interdisciplinary": "跨領域",
    "physics_astronomy": "物理／天文",
    "chemistry": "化學",
}

# name|slug|issn|publisher|categories|oa|status|enabled|source_id|direct_sources|origin
ROWS = r"""
ACS Central Science|acs-central-science||ACS|chemistry|fully_oa|planned|0|acs_central_science||
Artificial Intelligence|artificial-intelligence|0004-3702|Elsevier|llm_research|verify_per_work|active|1|elsevier_artificial_intelligence|crossref|
Artificial Intelligence in Medicine|artificial-intelligence-in-medicine|0933-3657|Elsevier|clinical_medicine,llm_research,human_ai|verify_per_work|active|1|elsevier_artificial_intelligence_medicine|crossref,pubmed,europe_pmc|
Chemical Science|chemical-science||Royal Society of Chemistry|chemistry|fully_oa|planned|0|chemical_science||
Clinical Biomechanics|clinical-biomechanics|0268-0033|Elsevier|sport_science,clinical_medicine|verify_per_work|active|1|elsevier_clinical_biomechanics|crossref,pubmed,europe_pmc|
Clinical Nutrition|clinical-nutrition|0261-5614|Elsevier|sport_nutrition_fitness,clinical_medicine|verify_per_work|active|1|elsevier_clinical_nutrition|crossref,pubmed,europe_pmc|
Clinical Nutrition ESPEN|clinical-nutrition-espen|2405-4577|Elsevier|sport_nutrition_fitness,clinical_medicine|verify_per_work|active|1|elsevier_clinical_nutrition_espen|crossref,pubmed,europe_pmc|
Clinical Nutrition Open Science|clinical-nutrition-open-science|2667-2685|Elsevier|sport_nutrition_fitness,clinical_medicine|verify_per_work|active|1|elsevier_clinical_nutrition_open_science|crossref,pubmed,europe_pmc|
Communications Chemistry|communications-chemistry||Nature Portfolio|chemistry|fully_oa|active|1|communications_chemistry|crossref|
Communications Physics|communications-physics||Nature Portfolio|physics_astronomy|fully_oa|active|1|communications_physics|crossref|
Computer Speech & Language|computer-speech-and-language|0885-2308|Elsevier|llm_research,human_ai|verify_per_work|active|1|elsevier_computer_speech_language|crossref|
Computers & Education: Artificial Intelligence|computers-and-education-artificial-intelligence|2666-920X|Elsevier|human_ai,llm_research|verify_per_work|active|1|elsevier_computers_education_ai|crossref|
Computers in Human Behavior|computers-in-human-behavior|0747-5632|Elsevier|human_ai|verify_per_work|active|1|elsevier_computers_human_behavior|crossref|
Computers in Human Behavior Reports|computers-in-human-behavior-reports|2451-9588|Elsevier|human_ai|verify_per_work|active|1|elsevier_computers_human_behavior_reports|crossref|
Computers in Human Behavior: Artificial Humans|computers-in-human-behavior-artificial-humans|2949-8821|Elsevier|human_ai,llm_research|verify_per_work|active|1|elsevier_computers_human_behavior_artificial_humans|crossref|
eClinicalMedicine|eclinicalmedicine|2589-5370|Lancet|clinical_medicine|verify_per_work|active|1|eclinicalmedicine|crossref,pubmed,europe_pmc|
Expert Systems with Applications|expert-systems-with-applications|0957-4174|Elsevier|llm_research|verify_per_work|active|1|elsevier_expert_systems_applications|crossref|
Gait & Posture|gait-and-posture|0966-6362|Elsevier|sport_science|verify_per_work|active|1|elsevier_gait_posture|crossref,pubmed,europe_pmc|
Human Movement Science|human-movement-science|0167-9457|Elsevier|sport_science|verify_per_work|active|1|elsevier_human_movement_science|crossref,pubmed,europe_pmc|
IEEE Transactions on Artificial Intelligence|ieee-transactions-on-artificial-intelligence|2691-4581|IEEE|llm_research|verify_per_work|active|1||crossref|editions
Information Processing & Management|information-processing-and-management|0306-4573|Elsevier|llm_research,human_ai|verify_per_work|active|1|elsevier_information_processing_management|crossref|
International Journal of Human-Computer Studies|international-journal-of-human-computer-studies|1071-5819|Elsevier|human_ai|verify_per_work|active|1|elsevier_international_journal_human_computer_studies|crossref|
JAMA Network Open|jama-network-open|2574-3805|JAMA Network|clinical_medicine|fully_oa|active|1|jama_network_open|pubmed,europe_pmc,crossref|
Journal of Biomedical Informatics|journal-of-biomedical-informatics|1532-0464|Elsevier|clinical_medicine,llm_research,human_ai|verify_per_work|active|1|elsevier_journal_biomedical_informatics|crossref,pubmed,europe_pmc|
Journal of Clinical Epidemiology|journal-of-clinical-epidemiology|0895-4356|Elsevier|clinical_medicine|verify_per_work|active|1|elsevier_journal_clinical_epidemiology|crossref,pubmed,europe_pmc|
Journal of Exercise Science & Fitness|journal-of-exercise-science-and-fitness|1728-869X|Elsevier|sport_science,sport_nutrition_fitness|verify_per_work|active|1|elsevier_jesf|crossref,pubmed,europe_pmc|
Journal of Machine Learning Research|journal-of-machine-learning-research||JMLR|llm_research|public_fulltext|planned|0|jmlr_first_party||
Journal of Science and Medicine in Sport|journal-of-science-and-medicine-in-sport|1440-2440|Elsevier|sport_science|verify_per_work|active|1|elsevier_jsams|crossref,pubmed,europe_pmc|
Journal of Sport and Health Science|journal-of-sport-and-health-science|2095-2546|Elsevier|sport_science|verify_per_work|active|1|elsevier_jshs|crossref,pubmed,europe_pmc|
Knowledge-Based Systems|knowledge-based-systems|0950-7051|Elsevier|llm_research|verify_per_work|active|1|elsevier_knowledge_based_systems|crossref|
Machine Learning|machine-learning|0885-6125|Springer Nature|llm_research|verify_per_work|active|1||crossref|editions
National Science Review|national-science-review||Oxford University Press|interdisciplinary|fully_oa|planned|0|national_science_review||
Natural Language Processing Journal|natural-language-processing-journal|2949-7191|Elsevier|llm_research|verify_per_work|active|1|elsevier_natural_language_processing_journal|crossref|
Nature Communications|nature-communications|2041-1723|Nature Portfolio|interdisciplinary|fully_oa|active|1|nature_communications|crossref,pubmed,europe_pmc|
Nature Machine Intelligence|nature-machine-intelligence|2522-5839|Nature Portfolio|llm_research,human_ai|mixed|active|1||crossref|editions
Neural Networks|neural-networks|0893-6080|Elsevier|llm_research|verify_per_work|active|1|elsevier_neural_networks|crossref|
Nutrition|nutrition|0899-9007|Elsevier|sport_nutrition_fitness,clinical_medicine|verify_per_work|active|1|elsevier_nutrition|crossref,pubmed,europe_pmc|
Nutrition Research|nutrition-research|0271-5317|Elsevier|sport_nutrition_fitness|verify_per_work|active|1|elsevier_nutrition_research|crossref,pubmed,europe_pmc|
Physical Review X|physical-review-x||American Physical Society|physics_astronomy|fully_oa|planned|0|physical_review_x||
Physical Therapy in Sport|physical-therapy-in-sport|1466-853X|Elsevier|sport_science|verify_per_work|active|1|elsevier_physical_therapy_sport|crossref,pubmed,europe_pmc|
PLOS Biology|plos-biology||PLOS|interdisciplinary|fully_oa|planned|0|plos_biology||
PLOS Medicine|plos-medicine||PLOS|clinical_medicine|fully_oa|planned|0|plos_medicine||
PNAS Nexus|pnas-nexus||PNAS / Oxford University Press|interdisciplinary|fully_oa|planned|0|pnas_nexus||
Psychology of Sport and Exercise|psychology-of-sport-and-exercise|1469-0292|Elsevier|sport_science|verify_per_work|active|1|elsevier_psychology_sport_exercise|crossref,pubmed,europe_pmc|
Science Advances|science-advances||AAAS|interdisciplinary|fully_oa|planned|0|science_advances||
Scientific Data|scientific-data||Nature Portfolio|interdisciplinary|fully_oa|planned|0|scientific_data||
Scientific Reports|scientific-reports||Nature Portfolio|interdisciplinary|fully_oa|active|1|scientific_reports|crossref,pubmed,europe_pmc|
Sports Medicine and Health Science|sports-medicine-and-health-science|2666-3376|Elsevier|sport_science|verify_per_work|active|1|elsevier_smhs|crossref,pubmed,europe_pmc|
The Journal of Nutritional Biochemistry|journal-of-nutritional-biochemistry|0955-2863|Elsevier|sport_nutrition_fitness|verify_per_work|active|1|elsevier_journal_nutritional_biochemistry|crossref,pubmed,europe_pmc|
The Lancet|the-lancet|0140-6736|Lancet|clinical_medicine|verify_per_work|active|1|lancet|crossref,pubmed,europe_pmc|
The Lancet Digital Health|the-lancet-digital-health|2589-7500|Lancet|clinical_medicine,llm_research,human_ai|verify_per_work|active|1|lancet_digital_health|crossref,pubmed,europe_pmc|
The Lancet Global Health|the-lancet-global-health|2214-109X|Lancet|clinical_medicine|verify_per_work|active|1|lancet_global_health|crossref,pubmed,europe_pmc|
The Lancet Healthy Longevity|the-lancet-healthy-longevity|2666-7568|Lancet|clinical_medicine,sport_nutrition_fitness|verify_per_work|active|1|lancet_healthy_longevity|crossref,pubmed,europe_pmc|
The Lancet Regional Health – Americas|the-lancet-regional-health-americas|2667-193X|Lancet|clinical_medicine|verify_per_work|active|1|lancet_regional_health_americas|crossref,pubmed,europe_pmc|
The Lancet Regional Health – Europe|the-lancet-regional-health-europe|2666-7762|Lancet|clinical_medicine|verify_per_work|active|1|lancet_regional_health_europe|crossref,pubmed,europe_pmc|
The Lancet Regional Health – Western Pacific|the-lancet-regional-health-western-pacific|2666-6065|Lancet|clinical_medicine|verify_per_work|active|1|lancet_regional_health_western_pacific|crossref,pubmed,europe_pmc|
Transactions of the Association for Computational Linguistics|tacl|2307-387X|ACL / MIT Press|llm_research,human_ai|fully_oa|planned|0|tacl_acl_anthology|crossref|
Transactions on Machine Learning Research|tmlr||TMLR / OpenReview|llm_research|public_fulltext|planned|0|tmlr_first_party||
""".strip()


def build_registry() -> dict:
    journals = []
    for line in ROWS.splitlines():
        parts = line.split("|")
        if len(parts) != 11:
            raise ValueError(f"bad row: {line}")
        name, slug, issn, publisher, categories, oa, status, enabled, source_id, sources, origin = parts
        item = {
            "name": name,
            "slug": slug,
            "publisher": publisher,
            "categories": [v for v in categories.split(",") if v],
            "oa": oa,
            "status": status,
        }
        if issn:
            item["issn"] = issn
        if enabled == "0":
            item["enabled"] = False
        if source_id:
            item["source_id"] = source_id
        direct = [v for v in sources.split(",") if v]
        if direct:
            item["sources"] = direct
        if origin:
            item["origin"] = origin
        journals.append(item)
    journals.sort(key=lambda value: value["name"].casefold())
    if len(journals) != 58:
        raise ValueError(f"expected 58 journals, got {len(journals)}")
    if len({value["slug"] for value in journals}) != len(journals):
        raise ValueError("duplicate journal slug")
    return {
        "schema_version": "2.0",
        "artifact_type": "EvidenceRadar_Editions_JournalRegistry",
        "semantics": "Local journal identity and direct acquisition defaults. Classification is metadata, not canonical URL identity.",
        "upstream": UPSTREAM,
        "category_labels": CATEGORY_LABELS,
        "journal_count": len(journals),
        "journals": journals,
    }


def main() -> None:
    path = Path("catalog/journals.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_registry(), ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
