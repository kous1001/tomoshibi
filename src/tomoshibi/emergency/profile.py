"""医療プロフィールの読込とバリデーション（端末ローカル・クラウド送信なし）。

境界での入力検証を徹底（外部ファイルは信頼しない）。欠損は安全側に補完する。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Resident:
    name: str = "ご本人"
    name_kana: str = ""
    age: int | None = None
    sex: str = ""
    address: str = ""
    phone: str = ""


@dataclass(frozen=True)
class Medical:
    blood_type: str = ""
    conditions: tuple[str, ...] = ()
    medications: tuple[str, ...] = ()
    allergies: tuple[str, ...] = ()
    mobility: str = ""
    primary_doctor: str = ""


@dataclass(frozen=True)
class Contact:
    name: str
    relation: str = ""
    phone: str = ""
    channel: str = "mock"


@dataclass(frozen=True)
class Profile:
    resident: Resident = field(default_factory=Resident)
    medical: Medical = field(default_factory=Medical)
    emergency_contacts: tuple[Contact, ...] = ()
    routine: dict[str, Any] = field(default_factory=dict)
    interests: tuple[str, ...] = ()


class ProfileError(ValueError):
    """プロフィールの読込/検証エラー。"""


def _as_str_tuple(v: Any) -> tuple[str, ...]:
    if not v:
        return ()
    if isinstance(v, str):
        return (v,)
    return tuple(str(x) for x in v)


def parse_profile(data: dict[str, Any]) -> Profile:
    """辞書から Profile を構築（欠損は安全に補完、型は強制）。"""
    if not isinstance(data, dict):
        raise ProfileError("プロフィールはJSONオブジェクトである必要があります")

    r = data.get("resident", {}) or {}
    m = data.get("medical", {}) or {}
    contacts_raw = data.get("emergency_contacts", []) or []

    age = r.get("age")
    try:
        age = int(age) if age is not None else None
    except (TypeError, ValueError):
        age = None

    contacts = tuple(
        Contact(
            name=str(c.get("name", "ご家族")),
            relation=str(c.get("relation", "")),
            phone=str(c.get("phone", "")),
            channel=str(c.get("channel", "mock")),
        )
        for c in contacts_raw
        if isinstance(c, dict)
    )

    return Profile(
        resident=Resident(
            name=str(r.get("name", "ご本人")),
            name_kana=str(r.get("name_kana", "")),
            age=age,
            sex=str(r.get("sex", "")),
            address=str(r.get("address", "")),
            phone=str(r.get("phone", "")),
        ),
        medical=Medical(
            blood_type=str(m.get("blood_type", "")),
            conditions=_as_str_tuple(m.get("conditions")),
            medications=_as_str_tuple(m.get("medications")),
            allergies=_as_str_tuple(m.get("allergies")),
            mobility=str(m.get("mobility", "")),
            primary_doctor=str(m.get("primary_doctor", "")),
        ),
        emergency_contacts=contacts,
        routine=data.get("routine", {}) or {},
        interests=_as_str_tuple(data.get("interests")),
    )


def load_profile(path: str | Path) -> Profile:
    """ファイルからプロフィールを読み込む。無ければ既定(空)を返す。"""
    p = Path(path)
    if not p.exists():
        # デモを止めない: 既定プロフィールにフォールバック
        return Profile()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ProfileError(f"プロフィールJSONの解析に失敗: {e}") from e
    return parse_profile(data)
