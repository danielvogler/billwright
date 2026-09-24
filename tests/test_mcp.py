"""The MCP surface, over the example profile.

The tools are thin by design, so what is worth asserting is that they are thin:
that a figure served over MCP is the one the engine computed, that every
response names the company it was billed as, and that nothing here can reach a
different number from the command line.
"""

import shutil
from pathlib import Path

import pytest

from billwright import mcp_server
from billwright.load import find_bill, load_company
from billwright.money import format_chf

fastmcp = pytest.importorskip("fastmcp", reason="the mcp extra is optional")


@pytest.fixture
def copied(profile, tmp_path):
    target = tmp_path / "profile"
    shutil.copytree(profile, target)
    return target


def test_summarise_names_the_company_and_its_profile(profile):
    result = mcp_server.summarise(profile)
    assert result["company"] == load_company(profile).name
    assert result["profile"] == str(profile)
    assert "example-institute" in result["clients"]
    assert "consulting" in result["services"]


def test_every_response_names_the_company_it_billed_as(profile):
    # Billing under the wrong company is worse than not billing, and a chat
    # client shows no working directory to notice it from.
    responses = [
        mcp_server.summarise(profile),
        mcp_server.bill_list(profile),
        mcp_server.bill_detail(profile, "RE-26001"),
        mcp_server.check(profile),
        mcp_server.doctor(profile),
    ]
    assert all(r["profile"] == str(profile) for r in responses)


def test_bill_list_reports_paid_status(profile):
    numbers = {b["number"]: b for b in mcp_server.bill_list(profile)["bills"]}
    assert numbers["RE-26001"]["paid_on"] is not None
    assert numbers["RE-26002"]["paid_on"] == "2027-01-14"


def test_bill_list_can_be_narrowed_to_a_year(profile):
    assert mcp_server.bill_list(profile, 2025)["bills"] == []


def test_the_total_served_is_the_total_the_engine_computes(profile):
    company = load_company(profile)
    expected = find_bill(profile, "RE-26001").total(company.effective_vat_rate)

    detail = mcp_server.bill_detail(profile, "RE-26001")

    assert detail["total"]["exact"] == str(expected)
    assert detail["total"]["chf"] == format_chf(expected)


def test_the_total_is_the_sum_of_the_lines_served_with_it(profile):
    from decimal import Decimal

    detail = mcp_server.bill_detail(profile, "RE-26001")
    lines = sum(Decimal(item["total"]["exact"]) for item in detail["items"])
    assert Decimal(detail["net"]["exact"]) == lines


def test_check_reads_the_example_profile_as_sound(profile):
    result = mcp_server.check(profile)
    assert result["ok"] is True
    assert result["problems"] == []


def test_doctor_reports_the_example_profile_ready(profile):
    assert mcp_server.doctor(profile)["ready"] is True


def test_scaffold_writes_the_next_number_with_no_amounts(copied):
    result = mcp_server.scaffold(copied, "example-institute", year=2026)

    written = (copied / "bills" / "2026" / f"{result['number']}.toml").read_text(encoding="utf-8")
    assert result["number"] == "RE-26003"
    assert "total" not in written
    assert "quantity = 0.0" in written


def test_scaffold_refuses_an_unknown_client(copied):
    with pytest.raises(Exception, match="example-missing|no such|unknown"):
        mcp_server.scaffold(copied, "example-missing")


def test_render_writes_a_pdf_and_reports_the_same_total(profile, tmp_path, assets):
    result = mcp_server.render_bill(profile, "RE-26001", assets=assets, out=tmp_path)

    company = load_company(profile)
    expected = find_bill(profile, "RE-26001").total(company.effective_vat_rate)
    assert result["archived"] is False
    assert result["total"]["exact"] == str(expected)
    written = Path(result["path"])
    assert written.parent == tmp_path
    assert written.exists()


def test_an_archived_bill_is_recorded_and_verifies(copied, tmp_path, assets):
    """Same record and same check as the command line: one engine, two doors."""
    archive_dir = tmp_path / "archive"
    result = mcp_server.render_bill(
        copied, "RE-26001", archive=True, assets=assets, archive_dir=archive_dir
    )

    assert result["archived"] is True
    assert list(archive_dir.rglob("*.provenance.json"))
    report = mcp_server.verify(copied, assets, archive_dir)
    assert report["ok"] is True
    assert len(report["verified"]) == 1


def test_statement_revenue_follows_paid_on(profile, tmp_path, assets):
    # RE-26002 is issued 2026-12-18 and paid 2027-01-14, so it is 2027 income.
    y2026 = mcp_server.render_statement(profile, 2026, assets=assets, out=tmp_path)
    y2027 = mcp_server.render_statement(profile, 2027, assets=assets, out=tmp_path)

    assert y2026["revenue"]["exact"] != y2027["revenue"]["exact"]
    assert len(y2026["paths"]) == 2


def test_the_server_exposes_agents_md_rather_than_restating_it(profile):
    import asyncio

    server = mcp_server.build_server(profile)
    result = asyncio.run(server.read_resource("billwright://agents"))

    assert "AGENTS.md" in str(result.contents)


def test_the_server_offers_the_documented_tools(profile):
    import asyncio

    server = mcp_server.build_server(profile)
    names = {tool.name for tool in asyncio.run(server.list_tools())}

    assert names == {
        "profile_info",
        "list_bills",
        "show_bill",
        "new_bill",
        "bill",
        "statement",
        "check_bills",
        "check_profile",
        "verify_archive",
    }
