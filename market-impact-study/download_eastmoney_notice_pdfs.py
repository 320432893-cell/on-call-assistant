"""Download selected Eastmoney notice PDFs from announcement codes."""

from __future__ import annotations

import csv
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

NOTICE_DIR = Path("market-impact-study/data/raw/akshare/eastmoney_individual_notice")
OUTPUT_DIR = Path("market-impact-study/data/documents/eastmoney_notice_pdfs")
MANIFEST_PATH = Path("market-impact-study/data/documents/eastmoney_notice_pdf_manifest.csv")
MAX_PER_COMPANY = 80

KEYWORDS = [
    "投资者关系",
    "调研",
    "业绩说明会",
    "业绩预告",
    "业绩快报",
    "年度报告",
    "半年度报告",
    "季度报告",
    "回购",
    "员工持股",
    "股权激励",
    "限制性股票",
    "定增",
    "非公开发行",
    "重大合同",
    "中标",
    "战略合作",
    "对外投资",
    "收购",
    "减持",
    "风险提示",
    "问询函",
    "关注函",
    "减值",
    "诉讼",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file_obj:
        return list(csv.DictReader(file_obj))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def extract_announcement_code(url: str) -> str:
    match = re.search(r"(AN\d+)", url or "")
    return match.group(1) if match else ""


def should_download(title: str, notice_type: str) -> bool:
    text = f"{title} {notice_type}"
    return any(keyword in text for keyword in KEYWORDS)


def download_pdf(code: str, output_path: Path) -> tuple[str, int, str]:
    url = f"https://pdf.dfcfw.com/pdf/H2_{code}_1.pdf"
    request = Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"},
    )
    try:
        with urlopen(request, timeout=12) as response:
            data = response.read()
        if not data.startswith(b"%PDF"):
            return "invalid", len(data), url
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(data)
        return "ok", len(data), url
    except HTTPError as exc:
        return f"http_{exc.code}", 0, url
    except URLError as exc:
        return f"url_error:{exc.reason}", 0, url
    except Exception as exc:  # noqa: BLE001
        return f"error:{type(exc).__name__}:{exc}", 0, url


def main() -> int:
    candidates: list[dict[str, str]] = []
    for csv_path in sorted(NOTICE_DIR.glob("*.csv")):
        if csv_path.name == "all_companies.csv":
            continue
        for row in read_csv(csv_path):
            title = row.get("公告标题", "")
            notice_type = row.get("公告类型", "")
            if should_download(title, notice_type):
                code = extract_announcement_code(row.get("网址", ""))
                if code:
                    row = dict(row)
                    row["announcement_code"] = code
                    candidates.append(row)

    grouped: dict[str, list[dict[str, str]]] = {}
    for row in candidates:
        grouped.setdefault(str(row.get("LOCAL_SYMBOL") or row.get("代码") or "unknown"), []).append(row)

    limited_candidates: list[dict[str, str]] = []
    for rows in grouped.values():
        limited_candidates.extend(rows[:MAX_PER_COMPANY])

    seen: set[str] = set()
    manifest: list[dict[str, object]] = []
    for index, row in enumerate(limited_candidates, start=1):
        code = row["announcement_code"]
        if code in seen:
            continue
        seen.add(code)
        symbol = row.get("LOCAL_SYMBOL") or row.get("代码") or "unknown"
        output_path = OUTPUT_DIR / str(symbol) / f"{code}.pdf"
        if output_path.exists() and output_path.stat().st_size > 0:
            status, size, pdf_url = "exists", output_path.stat().st_size, f"https://pdf.dfcfw.com/pdf/H2_{code}_1.pdf"
        else:
            status, size, pdf_url = download_pdf(code, output_path)
            time.sleep(0.12)
        manifest.append(
            {
                "company": row.get("LOCAL_COMPANY_NAME", ""),
                "symbol": symbol,
                "announcement_code": code,
                "title": row.get("公告标题", ""),
                "notice_type": row.get("公告类型", ""),
                "notice_date": row.get("公告日期", ""),
                "source_url": row.get("网址", ""),
                "pdf_url": pdf_url,
                "local_path": str(output_path) if status in {"ok", "exists"} else "",
                "status": status,
                "bytes": size,
            }
        )
        if index % 20 == 0:
            write_csv(
                MANIFEST_PATH,
                manifest,
                [
                    "company",
                    "symbol",
                    "announcement_code",
                    "title",
                    "notice_type",
                    "notice_date",
                    "source_url",
                    "pdf_url",
                    "local_path",
                    "status",
                    "bytes",
                ],
            )
            print(
                f"downloaded_checked={index}/{len(limited_candidates)} ok_or_exists={sum(1 for item in manifest if item['status'] in {'ok', 'exists'})}",
                flush=True,
            )

    write_csv(
        MANIFEST_PATH,
        manifest,
        [
            "company",
            "symbol",
            "announcement_code",
            "title",
            "notice_type",
            "notice_date",
            "source_url",
            "pdf_url",
            "local_path",
            "status",
            "bytes",
        ],
    )
    ok_count = sum(1 for row in manifest if row["status"] in {"ok", "exists"})
    invalid_count = sum(1 for row in manifest if row["status"] == "invalid")
    print(
        f"candidates={len(candidates)} limited={len(limited_candidates)} unique={len(manifest)} ok_or_exists={ok_count} invalid={invalid_count}"
    )
    print(f"manifest={MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
