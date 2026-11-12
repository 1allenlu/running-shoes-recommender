# Sample scans

`expected_profile.json` here is the fixture profile from a real scan (CLAUDE_CODE_PROMPT.md
section 4). The ranker tests and CLI use it.

For parser tests, add one folder per real Fleet Feet report:

```
data/sample_scans/
├── expected_profile.json     # the fixture
└── my-scan-2026-10/
    ├── 01.png                # screenshots (PNG/JPEG) or one report.pdf
    ├── 02.png
    └── expected_profile.json # hand-checked FootProfile; start from the fixture
```

`tests/test_scan_parser.py` sends each folder's report files to the parser and checks the
result: sizes and widths exact, bands equal, positions within ±0.15. It runs only when an LLM
key is set, and each run calls the API. `uv run python -m evals.run_evals --parser` scores
the same folders.

Positions run from 0.0 (left end of the scale) to 1.0 (right end). Leave `pressure` and
`arch_flexibility` as `null` if the report has no pressure-plate section.
