import shutil
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from trm_api import validate as validate_mod
from trm_api.lifecycle import lifecycle_state, risk_rating
from trm_api.loader import load
from trm_api.main import app

DATA = Path(__file__).parent / "fixtures" / "sample_data"
AS_OF = "2026-11-12"
client = TestClient(app)


# ---------------------------------------------------------------- loader / validator
def test_sample_data_loads_clean():
    repo = load(DATA)
    assert (len(repo.taxonomy), len(repo.technologies), len(repo.versions), len(repo.mappings)) == (5, 6, 13, 13)
    issues = validate_mod.all_issues(repo)
    assert [i for i in issues if i.level == "error"] == []
    warnings = [i for i in issues if i.level == "warning"]
    assert len(warnings) == 1 and "MAP-1002-01" in warnings[0].message


@pytest.fixture()
def data_copy(tmp_path):
    dst = tmp_path / "data"
    shutil.copytree(DATA, dst)
    return dst


def test_validator_catches_broken_references(data_copy):
    f = data_copy / "technologies" / "TECH-0003.md"
    f.write_text(f.read_text(encoding="utf-8").replace('"trm_id": "TRM-DB-002"', '"trm_id": "TRM-DB-999"'))
    m = data_copy / "mappings" / "APP-1005.md"
    m.write_text(m.read_text(encoding="utf-8").replace('"version": "16"', '"version": "99"'))
    msgs = [i.message for i in validate_mod.all_issues(load(data_copy)) if i.level == "error"]
    assert any("TRM-DB-999" in x for x in msgs)
    assert any("'99' is not registered" in x for x in msgs)


def test_validator_catches_schema_and_filename_errors(data_copy):
    f = data_copy / "technologies" / "TECH-0001.md"
    f.write_text(f.read_text(encoding="utf-8").replace('"Disinvest"', '"Retire"').replace('"it_owner"', '"ownr"'))
    (data_copy / "taxonomy" / "TRM-DB-002.md").rename(data_copy / "taxonomy" / "TRM-DB-077.md")
    msgs = " | ".join(i.message for i in load(data_copy).issues)
    assert "status" in msgs and "ownr" in msgs and "file name must equal" in msgs


def test_bad_json_is_reported_not_raised(data_copy):
    (data_copy / "taxonomy" / "TRM-DB-003.md").write_text("# x\n```json\n{ not json }\n```\n", encoding="utf-8")
    repo = load(data_copy)
    assert any("invalid JSON" in i.message for i in repo.issues)
    assert len(repo.taxonomy) == 4


def test_cli_exit_codes(data_copy):
    assert validate_mod.main(["--data-dir", str(data_copy)]) == 0
    assert validate_mod.main(["--data-dir", str(data_copy), "--strict"]) == 1  # sample has 1 warning


# ---------------------------------------------------------------- lifecycle rules
D = date(2026, 11, 12)


@pytest.mark.parametrize("eol,eos,expected", [
    (None, None, "Not Dated"),
    (date(2022, 3, 31), date(2025, 3, 31), "Out of Support"),
    (date(2026, 4, 30), date(2030, 4, 30), "Past End of Life"),
    (date(2026, 11, 26), date(2026, 11, 26), "Nearing End of Life"),
    (date(2029, 12, 31), date(2032, 12, 31), "Supported"),
    (None, date(2027, 1, 1), "Nearing End of Life"),
    (date(2026, 1, 1), None, "Past End of Life"),
])
def test_lifecycle_state(eol, eos, expected):
    assert lifecycle_state(eol, eos, D) == expected


def test_risk_rules():
    assert risk_rating("Out of Support", "Invest") == "High"
    assert risk_rating("Supported", "Disinvest") == "Medium"
    assert risk_rating("Supported", "Invest") == "Low"


# ---------------------------------------------------------------- API
def test_health():
    r = client.get("/health").json()
    assert r["status"] == "ok" and r["errors"] == 0 and r["records"]["technologies"] == 6


def test_status_filter_matches_brief():
    r = client.get("/v1/technologies", params={"as_of": AS_OF}).json()
    status = {t["technology_name"]: t["status"] for t in r}
    assert status == {
        "Oracle Database": "Disinvest", "Microsoft SQL Server": "Invest", "PostgreSQL": "Invest",
        "Qlik Sense": "Disinvest", "Microsoft Power BI": "Invest", "IBM Cognos Analytics": "Disinvest",
    }
    only = client.get("/v1/technologies", params={"status": "disinvest", "domain": "databases", "as_of": AS_OF}).json()
    assert [t["technology_name"] for t in only] == ["Oracle Database"]
    bi = client.get("/v1/technologies", params={"it_owner": "head of bi & analytics", "as_of": AS_OF}).json()
    assert len(bi) == 3 and all(t["entity"] == "Group" for t in bi)


def test_technology_detail_joins_everything():
    r = client.get("/v1/technologies/TECH-0001", params={"as_of": AS_OF}).json()
    assert (r["domain"], r["area"], r["category"]) == ("Databases", "Relational Databases", "Commercial RDBMS")
    assert r["sme"] == "Lead DBA" and r["support_team"] == "DBA Operations"
    assert {v["version"]: v["lifecycle_state"] for v in r["versions"]} == {
        "12.2.0.1": "Out of Support", "19c": "Supported"}
    assert {a["application_id"] for a in r["applications"]} == {"APP-1001", "APP-1002", "APP-1004"}
    assert "Standard position" in r["narrative"]
    assert client.get("/v1/technologies/TECH-9999").status_code == 404


def test_reports_match_hand_calculation():
    s = client.get("/v1/reports/summary", params={"as_of": AS_OF}).json()
    assert s["mapping_risk"] == {"High": 2, "Medium": 7, "Low": 4}
    assert s["versions_by_lifecycle_state"] == {
        "Out of Support": 2, "Past End of Life": 2, "Nearing End of Life": 3, "Supported": 4, "Not Dated": 2}
    assert s["technologies_by_status"] == {"Disinvest": 3, "Invest": 3}
    high = client.get("/v1/mappings", params={"risk_rating": "High", "as_of": AS_OF}).json()
    assert {m["mapping_id"] for m in high} == {"MAP-1002-01", "MAP-1007-01"}
    exp = client.get("/v1/reports/disinvest-exposure", params={"as_of": AS_OF}).json()
    oracle = next(e for e in exp if e["technology_name"] == "Oracle Database")
    assert oracle["application_count"] == 3 and oracle["applications_without_retirement_date"] == ["APP-1002"]
    gaps = [n["trm_id"] for n in client.get("/v1/reports/taxonomy-coverage").json() if n["gap"]]
    assert gaps == ["TRM-DB-003"]


def test_as_of_changes_derived_state():
    later = client.get("/v1/versions", params={"tech_id": "TECH-0004", "as_of": "2027-01-01"}).json()
    assert {v["version"]: v["lifecycle_state"] for v in later}["November 2024"] == "Out of Support"


def test_csv_exports():
    for ds, header in [("taxonomy", "trm_id,domain,area,category,status"),
                       ("technologies", "tech_id,entity,technology_name,trm_id"),
                       ("versions", "version_id,tech_id"), ("mappings", "mapping_id,application_id")]:
        r = client.get(f"/v1/export/{ds}.csv", params={"as_of": AS_OF})
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
        assert r.text.startswith(header)
    lines = client.get("/v1/export/mappings.csv", params={"as_of": AS_OF}).text.strip().splitlines()
    assert len(lines) == 14 and "Prod|DR|UAT" in lines[1]
    assert client.get("/v1/export/nope.csv").status_code == 404


def test_raw_and_search_and_traversal():
    raw = client.get("/v1/raw/technologies/TECH-0003")
    assert raw.status_code == 200 and '"tech_id": "TECH-0003"' in raw.text
    assert client.get("/v1/raw/technologies/..%2F..%2FREADME").status_code == 404
    names = {h["name"] for h in client.get("/v1/search", params={"q": "oracle"}).json()}
    assert "Oracle Database" in names
    assert "Oracle Database" in {h["name"] for h in client.get("/v1/search", params={"q": "dba operations"}).json()}


def test_api_key_enforced_when_configured(monkeypatch):
    monkeypatch.setenv("TRM_API_KEY", "s3cret")
    assert client.get("/v1/taxonomy").status_code == 401
    assert client.get("/v1/taxonomy", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/v1/taxonomy", headers={"X-API-Key": "s3cret"}).status_code == 200
    assert client.get("/health").status_code == 200


def test_export_cli(tmp_path):
    from trm_api.exports import main
    assert main(["--out", str(tmp_path), "--as-of", AS_OF, "--data-dir", str(DATA)]) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == ["mappings.csv", "taxonomy.csv", "technologies.csv", "versions.csv"]


# ---------------------------------------------------------------- importer
from trm_api import import_csv  # noqa: E402

CSV_DIR = Path(__file__).parent / "fixtures" / "csv"
SAMPLE_DIR = Path(__file__).parent / "fixtures" / "sample_data"


def _args(data_dir, *extra):
    return ["--taxonomy", str(CSV_DIR / "taxonomy.csv"), "--technologies", str(CSV_DIR / "technologies.csv"),
            "--data-dir", str(data_dir), *extra]


def test_import_creates_files_and_is_idempotent(tmp_path, capsys):
    d = tmp_path / "data"
    assert import_csv.main(_args(d)) == 0
    assert len(list((d / "taxonomy").glob("*.md"))) == 5 and len(list((d / "technologies").glob("*.md"))) == 6
    repo = load(d)
    assert [i for i in repo.issues if i.level == "error" and "folder is missing" not in i.message] == []
    assert {t.technology_name for t in repo.technologies if t.status.value == "Disinvest"} == {
        "Oracle Database", "Qlik Sense", "IBM Cognos Analytics"}
    before = {p: p.read_text(encoding="utf-8") for p in d.rglob("*.md")}
    capsys.readouterr()
    assert import_csv.main(_args(d)) == 0
    assert "create 0, update 0, unchanged 6" in capsys.readouterr().out
    assert before == {p: p.read_text(encoding="utf-8") for p in d.rglob("*.md")}


def test_import_keeps_prose_and_updates_record(data_copy, tmp_path):
    csv_in = tmp_path / "t.csv"
    csv_in.write_text("Tech ID,Entity,Technology Name,TRM ID,Status,SME,IT Owner,Support Team,comments\n"
                      "TECH-0003,Group,PostgreSQL,TRM-DB-002,maintain,New SME,Head of Data Platforms,DBA Ops,\n", encoding="utf-8")
    assert import_csv.main(["--technologies", str(csv_in), "--data-dir", str(data_copy)]) == 0
    text = (data_copy / "technologies" / "TECH-0003.md").read_text(encoding="utf-8")
    assert '"status": "Maintain"' in text and '"sme": "New SME"' in text and "comments" not in text
    assert "## Standard position" in text                       # prose survived
    assert (data_copy / "technologies" / "TECH-0001.md").read_text(encoding="utf-8").count("Oracle Database") >= 1  # others untouched


def test_import_is_all_or_nothing_with_row_numbers(data_copy, tmp_path, capsys):
    csv_in = tmp_path / "t.csv"
    csv_in.write_text(
        "Tech ID,Entity,Technology Name,TRM ID,Status,SME,IT Owner,Support Team,comments\n"
        "TECH-0003,Group,PostgreSQL,TRM-DB-002,Maintain,x,y,z,\n"        # valid
        "TECH-0009,Group,MongoDB,TRM-DB-003,Keep,x,y,z,\n"                # bad status
        "TECH-0010,Group,Redis,TRM-XX-999,Invest,x,y,z,\n"                # unknown TRM ID
        "TECH-0003,Group,Dup,TRM-DB-002,Invest,x,y,z,\n"                  # duplicate id
        "TECH-0011,,NoEntity,TRM-DB-002,Invest,x,y,z,\n", encoding="utf-8")                 # missing entity
    before = (data_copy / "technologies" / "TECH-0003.md").read_text(encoding="utf-8")
    assert import_csv.main(["--technologies", str(csv_in), "--data-dir", str(data_copy)]) == 1
    out = capsys.readouterr().out
    assert "row 3 (TECH-0009): Status" in out and "row 5 (TECH-0003): duplicate ID" in out
    assert "row 6 (TECH-0011): Entity" in out and "'TRM-XX-999' is not in the taxonomy" in out
    assert (data_copy / "technologies" / "TECH-0003.md").read_text(encoding="utf-8") == before
    assert not (data_copy / "technologies" / "TECH-0009.md").exists()


def test_import_header_variants_missing_column_and_bom(data_copy, tmp_path, capsys):
    ok = tmp_path / "ok.csv"
    ok.write_text("\ufefftrm_id,DOMAIN,area , Category,STATUS,Extra\nTRM-NEW-001,D,A,C,active,ignored\n", encoding="utf-8")
    assert import_csv.main(["--taxonomy", str(ok), "--data-dir", str(data_copy)]) == 0
    assert "ignoring unknown column(s): Extra" in capsys.readouterr().out
    assert (data_copy / "taxonomy" / "TRM-NEW-001.md").read_text(encoding="utf-8").startswith("# D › A › C")
    bad = tmp_path / "bad.csv"
    bad.write_text("TRM ID,Domain\nTRM-X-1,D\n", encoding="utf-8")
    assert import_csv.main(["--taxonomy", str(bad), "--data-dir", str(data_copy)]) == 1
    assert "missing required column(s): Area, Category, Status" in capsys.readouterr().out


def test_import_dry_run_and_templates(tmp_path, capsys):
    d = tmp_path / "data"
    assert import_csv.main(_args(d, "--dry-run")) == 0
    assert not d.exists()
    assert import_csv.main(["--make-templates", str(tmp_path / "tpl")]) == 0
    assert (tmp_path / "tpl" / "technologies_template.csv").read_text(encoding="utf-8").strip() == \
        "Tech ID,Entity,Technology Name,TRM ID,Status,SME,IT Owner,Support Team,comments"


def test_import_excel_with_sheet_name(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Taxonomy"
    ws.append(["TRM ID", "Domain", "Area", "Category", "Status"])
    ws.append(["TRM-XL-001", "Databases", "Relational Databases", "Cloud RDBMS", "Active"])
    ws2 = wb.create_sheet("Other")
    ws2.append(["junk"])
    f = tmp_path / "trm.xlsx"
    wb.save(f)
    d = tmp_path / "data"
    assert import_csv.main(["--taxonomy", f"{f}::Taxonomy", "--data-dir", str(d)]) == 0
    assert (d / "taxonomy" / "TRM-XL-001.md").exists()
    assert import_csv.main(["--taxonomy", f"{f}::Nope", "--data-dir", str(d)]) == 1


# ---- versions / mappings importers -------------------------------------------------
def _full(d, *extra):
    return [*_args(d), "--versions", str(CSV_DIR / "versions.csv"), "--mappings", str(CSV_DIR / "mappings.csv"),
            *extra]


def _snapshot(d):
    r = load(Path(d))
    return {k: [x.model_dump(mode="json") for x in getattr(r, k)]
            for k in ("taxonomy", "technologies", "versions", "mappings")}


def test_import_all_four_reproduces_sample_data_and_is_idempotent(tmp_path, capsys):
    d = tmp_path / "data"
    assert import_csv.main(_full(d)) == 0
    assert _snapshot(d) == _snapshot(SAMPLE_DIR)
    capsys.readouterr()
    assert import_csv.main(_full(d)) == 0
    out = capsys.readouterr().out
    assert "create 0, update 0" in out and "~" not in out and "+" not in out


def _prep(tmp_path):
    d = tmp_path / "data"
    assert import_csv.main(_args(d)) == 0
    assert import_csv.main(["--versions", str(CSV_DIR / "versions.csv"), "--data-dir", str(d)]) == 0
    return d


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_mappings_merge_rows_generate_ids_and_lenient_dates(tmp_path):
    d = _prep(tmp_path)
    f = _write(tmp_path / "m.csv",
               "Application ID,Application Name,Tech ID,Version,Environments,Usage,Planned Retirement Date\n"
               "APP-9001,Demo App,TECH-0002,2022,prod,Core,31/12/2030\n"
               "APP-9001,Demo App,TECH-0002,2022,Development,,\n"
               "APP-9001,Demo App,TECH-0003,16,\"Prod, DR\",Reporting,TBD\n")
    assert import_csv.main(["--mappings", f, "--data-dir", str(d)]) == 0
    m = {(x.tech_id, x.version): x for x in load(d).mappings if x.application_id == "APP-9001"}
    a = m[("TECH-0002", "2022")]
    assert a.environments == ["Prod", "Dev"] and a.usage == "Core" and str(a.planned_retirement_date) == "2030-12-31"
    assert a.mapping_id == "MAP-9001-01" and m[("TECH-0003", "16")].mapping_id == "MAP-9001-02"
    assert m[("TECH-0003", "16")].planned_retirement_date is None


def test_mappings_errors_are_all_reported_and_nothing_written(tmp_path, capsys):
    d = _prep(tmp_path)
    before = _snapshot(d)
    f = _write(tmp_path / "m.csv",
               "Application ID,Application Name,Tech ID,Version,Environments,Usage,Planned Retirement Date\n"
               "APP-9001,A,TECH-9999,1,Prod,x,\n"
               "APP-9001,A,TECH-0002,1999,Prod,x,\n"
               "APP-9001,A,TECH-0002,2022,Mars,x,notadate\n"
               "APP-9001,Other name,TECH-0002,2022,Prod,x,\n")
    assert import_csv.main(["--mappings", f, "--data-dir", str(d)]) == 1
    out = capsys.readouterr().out
    for needle in ("TECH-9999", "1999", "Mars", "notadate", "differs"):
        assert needle in out
    assert "row 4" in out and _snapshot(d) == before


def test_mapping_conflict_between_rows_for_same_pair(tmp_path, capsys):
    d = _prep(tmp_path)
    f = _write(tmp_path / "m.csv",
               "Application ID,Application Name,Tech ID,Version,Environments,Usage\n"
               "APP-9001,A,TECH-0002,2022,Prod,Core\n"
               "APP-9001,A,TECH-0002,2022,DR,Different\n")
    assert import_csv.main(["--mappings", f, "--data-dir", str(d)]) == 1
    assert "conflicts" in capsys.readouterr().out


def test_versions_merge_keeps_existing_and_replace_drops(tmp_path):
    d = _prep(tmp_path)
    f = _write(tmp_path / "v.csv", "Tech ID,Version,EOL date,EOS date\nTECH-0001,23ai,2030-01-01,2032-01-01\n")
    assert import_csv.main(["--versions", f, "--data-dir", str(d)]) == 0
    v = {x.version: x for x in load(d).versions if x.tech_id == "TECH-0001"}
    assert set(v) == {"12.2.0.1", "19c", "23ai"}
    assert v["23ai"].version_id == "TECH-0001-V003" and v["19c"].details  # details preserved: column absent
    assert import_csv.main(["--versions", f, "--data-dir", str(d), "--replace"]) == 0
    assert [x.version for x in load(d).versions if x.tech_id == "TECH-0001"] == ["23ai"]


def test_versions_unknown_tech_and_bad_dates(tmp_path, capsys):
    d = _prep(tmp_path)
    f = _write(tmp_path / "v.csv", "Tech ID,Version,EOL date,EOS date\nTECH-9999,1,,\nTECH-0001,2,2030-01-01,2029-01-01\n")
    assert import_csv.main(["--versions", f, "--data-dir", str(d)]) == 1
    out = capsys.readouterr().out
    assert "TECH-9999" in out and "row 3" in out


def test_mapping_blank_cell_clears_but_absent_column_preserves(tmp_path):
    d = _prep(tmp_path)
    assert import_csv.main(["--mappings", str(CSV_DIR / "mappings.csv"), "--data-dir", str(d)]) == 0
    f = _write(tmp_path / "m.csv", "Application ID,Application Name,Tech ID,Version,Usage\n"
                                   "APP-1002,Trade Capture & Order Management,TECH-0001,12.2.0.1,\n")
    assert import_csv.main(["--mappings", f, "--data-dir", str(d)]) == 0
    m = next(x for x in load(d).mappings if x.application_id == "APP-1002")
    assert m.usage is None and m.environments == ["Prod", "DR"] and m.notes


def test_import_excel_versions_sheet(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    d = _prep(tmp_path)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Versions"
    ws.append(["Tech ID", "Version", "EOL date", "EOS date"])
    ws.append(["TECH-0004", 17, date(2030, 1, 1), date(2031, 1, 1)])
    p = tmp_path / "trm.xlsx"
    wb.save(p)
    assert import_csv.main(["--versions", f"{p}::Versions", "--data-dir", str(d)]) == 0
    assert any(x.version == "17" and str(x.eol_date) == "2030-01-01" for x in load(d).versions)
