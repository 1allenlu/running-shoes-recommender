# Sample scans

One folder per real Fleet Feet report, used by `tests/test_scan_parser.py`:

```
data/sample_scans/
└── my-scan-2026-10/
    ├── 01.png            # screenshots (PNG/JPEG) or one report.pdf
    ├── 02.png
    └── expected.json     # hand-checked FootProfile; start from expected.template.json
```

The test sends each folder's report files to the parser and checks the result against
`expected.json`: sizes and widths exact, bands equal, positions within ±0.15.
It runs only when `ANTHROPIC_API_KEY` is set, and each run calls the API.

Positions run from 0.0 (left end of the scale) to 1.0 (right end). Leave `pressure` and
`arch_flexibility` as `null` if the report has no pressure-plate section.
