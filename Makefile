.PHONY: test lint fixture validate package clean

lint:
	ruff check .

test:
	pytest

fixture:
	rm -rf outputs/fixture
	evidenceradar-editions build --collection config/collections/jama-network-open.yml --start 2026-08-01 --end 2026-08-31 --fixture-dir tests/fixtures --strict-sources --output outputs/fixture

validate:
	evidenceradar-editions validate outputs/fixture

package:
	python -m build

clean:
	rm -rf build dist .pytest_cache .ruff_cache outputs *.egg-info src/*.egg-info
