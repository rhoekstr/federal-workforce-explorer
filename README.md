# Federal Workforce Explorer

Static, privacy-first dashboard over OPM Federal Workforce Data, PLUM, USAspending, and OMB FTE. Requirements and data model in [PRD.md](PRD.md); build plan in [RUNBOOK.md](RUNBOOK.md); repo rules in [CLAUDE.md](CLAUDE.md).

```bash
python3 -m venv .venv && .venv/bin/pip install -r pipeline/requirements.txt
.venv/bin/python -m pipeline.cli --help
.venv/bin/pytest
```
