"""법제처 Open API 최소 수집 스크립트 (1단계).

사용법 (등록한 IP의 PC에서 실행):
    python scripts/collect.py check   # 인증/IP/신청항목 점검
    python scripts/collect.py laws    # 대상 법령 본문 XML을 data/raw/law/ 에 저장

주의: 필드명은 공식 가이드 기준이라 실제 응답과 다를 수 있다.
실패하면 data/raw/law/_search/ 에 저장된 응답을 보고 고친다.
"""
import json
import sys
from pathlib import Path

import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "law"
SEARCH_DIR = RAW / "_search"
BASE = "http://www.law.go.kr/DRF"

TARGET_LAWS = [
    "주택임대차보호법",
    "주택임대차보호법 시행령",
    "민법",
]


def get_oc() -> str:
    oc = dotenv_values(ROOT / ".env").get("LAW_OC")
    if not oc or oc.startswith("여기에"):
        sys.exit("`.env`에 LAW_OC(인증키)를 설정하세요. (.env.example 참고)")
    return oc


def find_items(node):
    """응답 JSON 어디에 있든 '법령일련번호'를 가진 dict 목록을 찾는다."""
    if isinstance(node, dict):
        if "법령일련번호" in node:
            return [node]
        out = []
        for v in node.values():
            out += find_items(v)
        return out
    if isinstance(node, list):
        out = []
        for v in node:
            out += find_items(v)
        return out
    return []


def search_law(oc: str, name: str) -> list[dict]:
    r = requests.get(
        f"{BASE}/lawSearch.do",
        params={"OC": oc, "target": "law", "type": "JSON", "query": name, "display": 20},
        timeout=30,
    )
    r.raise_for_status()
    SEARCH_DIR.mkdir(parents=True, exist_ok=True)
    (SEARCH_DIR / f"{name}.json").write_text(r.text, encoding="utf-8")
    try:
        return find_items(r.json())
    except ValueError:
        sys.exit(f"JSON이 아닌 응답입니다. {SEARCH_DIR / (name + '.json')} 를 확인하세요 "
                 "(IP 미등록 / 미신청 항목 / 인증키 오류 가능).")


def pick_current(items: list[dict], name: str) -> dict | None:
    exact = [i for i in items if i.get("법령명한글") == name]
    current = [i for i in exact if i.get("현행연혁코드") == "현행"]
    return (current or exact or [None])[0]


def cmd_check(oc: str):
    items = search_law(oc, "주택임대차보호법")
    print(f"검색 결과 {len(items)}건")
    for i in items[:5]:
        print(" -", i.get("법령명한글"), i.get("법령일련번호"), i.get("현행연혁코드"))
    if not items:
        print("결과가 없습니다. data/raw/law/_search/ 의 응답을 확인하세요.")


def cmd_laws(oc: str):
    RAW.mkdir(parents=True, exist_ok=True)
    for name in TARGET_LAWS:
        item = pick_current(search_law(oc, name), name)
        if not item:
            print(f"[실패] {name}: 검색 결과에서 찾지 못함")
            continue
        mst = item["법령일련번호"]
        r = requests.get(
            f"{BASE}/lawService.do",
            params={"OC": oc, "target": "law", "MST": mst, "type": "XML"},
            timeout=60,
        )
        r.raise_for_status()
        path = RAW / f"{name}_{mst}.xml"
        path.write_text(r.text, encoding="utf-8")
        print(f"[저장] {path.relative_to(ROOT)} ({len(r.text):,}자)")


if __name__ == "__main__":
    cmds = {"check": cmd_check, "laws": cmd_laws}
    if len(sys.argv) != 2 or sys.argv[1] not in cmds:
        sys.exit("사용법: python scripts/collect.py [check|laws]")
    cmds[sys.argv[1]](get_oc())
