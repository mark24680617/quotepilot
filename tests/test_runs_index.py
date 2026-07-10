from quotepilot.web.runs_index import list_runs

def test_missing_runs_dir(tmp_path):
    result = list_runs(tmp_path / "nonexistent", limit=50)
    assert result == []

def test_full_happy_run_dir(tmp_path):
    run_dir = tmp_path / "20260103-000000-cc"
    run_dir.mkdir()

    # Create audit.jsonl
    audit_path = run_dir / "audit.jsonl"
    audit_path.write_text(
        '{"event":"run_started","ts":"2026-01-03T00:00:00Z"}\n'
        '{"event":"run_finished","decision":"approve"}\n'
    )

    # Create quote.json
    quote_path = run_dir / "quote.json"
    quote_path.write_text(
        '{"quote_number":"Q12345","total_usd":"1000.00","customer":{"company":"Acme Inc"}}'
    )

    # Create HTML file
    html_path = run_dir / "Q12345.html"
    html_path.write_text("<html>Approved</html>")

    result = list_runs(tmp_path, limit=50)
    assert len(result) == 1
    entry = result[0]
    assert entry.run_id == "20260103-000000-cc"
    assert entry.ts == "2026-01-03T00:00:00Z"
    assert entry.quote_number == "Q12345"
    assert entry.company == "Acme Inc"
    assert entry.total_usd == "1000.00"
    assert entry.decision == "approve"
    assert entry.has_html is True

def test_partial_dir_malformed_quote_json(tmp_path):
    run_dir = tmp_path / "20260101-000000-aa"
    run_dir.mkdir()

    # Create audit.jsonl
    audit_path = run_dir / "audit.jsonl"
    audit_path.write_text(
        '{"event":"run_started","ts":"2026-01-01T00:00:00Z"}\n'
    )

    # Malformed quote.json
    quote_path = run_dir / "quote.json"
    quote_path.write_text("not json")

    result = list_runs(tmp_path, limit=50)
    assert len(result) == 1
    entry = result[0]
    assert entry.run_id == "20260101-000000-aa"
    assert entry.ts == "2026-01-01T00:00:00Z"
    assert entry.quote_number is None
    assert entry.company is None
    assert entry.total_usd is None
    assert entry.decision is None
    assert entry.has_html is False

def test_ordering_and_limit(tmp_path):
    # Create three directories with increasing timestamps
    dirs = [
        tmp_path / "20260101-000000-aa",
        tmp_path / "20260102-000000-bb",
        tmp_path / "20260103-000000-cc"
    ]
    for d in dirs:
        d.mkdir()

    # Add minimal content to each
    for i, d in enumerate(dirs):
        audit_path = d / "audit.jsonl"
        audit_path.write_text(f'{{"event":"run_started","ts":"2026-01-{i+1:02d}-00:00:00Z"}}\n')

    result = list_runs(tmp_path, limit=2)
    assert len(result) == 2
    assert result[0].run_id == "20260103-000000-cc"
    assert result[1].run_id == "20260102-000000-bb"
