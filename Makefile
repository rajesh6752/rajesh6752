.PHONY: assets check recent preview

# Re-render assets/*.svg from profile.toml.
assets:
	python3 scripts/render_assets.py

# Fail if committed assets are stale (same check CI runs).
check:
	python3 scripts/render_assets.py --check

# Refresh the "Recently active" table locally (needs GITHUB_TOKEN or GH_TOKEN).
recent:
	python3 scripts/update_recent.py

# Print the table without touching README.md.
preview:
	python3 scripts/update_recent.py --dry-run
