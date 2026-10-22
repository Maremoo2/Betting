"""Offline, retrospective ATG identity corroboration; never provider admission."""
import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path

from .date_overview import DailyArchive, timestamp
from .provider_capability import name_key


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def biography(text):
    match = re.fullmatch(r"(\d+)-års .+? (v|h|hp) e (.+?) - (.+?) e .+", text.strip())
    if not match:
        return None
    age, sex, sire, dam = match.groups()
    return int(age), {"v": "gelding", "h": "stallion", "hp": "mare"}[sex], name_key(sire), name_key(dam)


def resolve(archive, evidence_path, evidence_sha):
    raw = Path(evidence_path).read_bytes()
    if sha(raw) != evidence_sha:
        raise ValueError("ATG_ARCHIVE_HASH_MISMATCH")
    with zipfile.ZipFile(evidence_path) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or sum(i.file_size for i in z.infolist()) > 100_000_000:
            raise ValueError("INVALID_EVIDENCE_ZIP")
        manifest = json.loads(z.read("manifest.json"))
        if manifest["schema"] != "ATG_SE_IDENTITY_ARCHIVE_V1":
            raise ValueError("UNKNOWN_EVIDENCE_SCHEMA")
        files = {}
        for member, expected in manifest["files_sha256"].items():
            data = z.read(member)
            if sha(data) != expected:
                raise ValueError("ATG_MEMBER_HASH_MISMATCH")
            files[member] = json.loads(data)
    calendar = files["calendar.json"]
    expected_calendar = f"https://horse-betting-info.prod.c1.atg.cloud/api-public/v0/calendar/day/{archive.day}?headToHeadEnabled=true"
    if calendar["url"] != expected_calendar:
        raise ValueError("UNTRUSTED_CALENDAR_SOURCE")
    if not calendar["success"] or calendar["status_code"] != 200 or calendar["payload"]["date"] != archive.day:
        raise ValueError("CALENDAR_NOT_VERIFIED")
    links = []
    for doc_index, doc in enumerate(archive.data["races"]):
        race = doc["race"]
        meeting = next(m for m in archive.manifest["meetings"] if m["meeting_id"] == race["meeting_id"])
        listing = meeting.get("listing_source", {})
        if listing.get("country") != "SE" or listing.get("sport_type") != "T":
            continue
        candidates = []
        for track in calendar["payload"]["tracks"]:
            if track.get("countryCode") == "SE" and name_key(track["name"]) == name_key(race["track"]):
                for cr in track["races"]:
                    if cr["number"] == race["race_number"] and track.get("sport") == "trot":
                        candidates.append(cr["id"])
        mid, number = race["meeting_id"], race["race_number"]
        starts_member = f"meetings/{mid}/starts.json"
        original = archive.read(starts_member)["response"]["result"][str(number)]
        reasons = []
        envelope, provider_race, member = None, None, None
        if len(candidates) != 1:
            reasons.append("RACE_IDENTITY_UNRESOLVED")
        else:
            member = f"races/{candidates[0]}.json"
            envelope = files.get(member)
            if not envelope or not envelope["success"] or envelope["status_code"] != 200:
                reasons.append("AUTHORITATIVE_RESPONSE_MISSING")
            else:
                if envelope["url"] != f"https://www.atg.se/services/racinginfo/v1/api/games/vinnare_{candidates[0]}":
                    raise ValueError("UNTRUSTED_IDENTITY_SOURCE")
                timestamp(envelope["observed_at"])
                payload_races = envelope["payload"].get("races", [])
                if len(payload_races) != 1:
                    reasons.append("AMBIGUOUS_PROVIDER_RACE")
                else:
                    provider_race = payload_races[0]
                    if (provider_race["id"] != candidates[0] or provider_race["date"] != archive.day
                            or provider_race["number"] != number or provider_race["sport"] != "trot"
                            or provider_race["track"]["countryCode"] != "SE"
                            or name_key(provider_race["track"]["name"]) != name_key(race["track"])):
                        reasons.append("RACE_METADATA_CONFLICT")
        field = provider_race.get("starts", []) if provider_race else []
        expected = {int(h["startNumber"]): name_key(h["horseName"]) for h in original}
        observed = {h["number"]: name_key(h["horse"]["name"]) for h in field}
        if (len(expected) != len(original) or len(observed) != len(field) or expected != observed
                or len(set(expected.values())) != len(expected)
                or len(set(observed.values())) != len(observed)
                or len({h["horse"]["id"] for h in field}) != len(field)):
            reasons.append("FULL_FIELD_OR_NAME_COLLISION")
        pdf = {h["program_number"]: h for h in doc["entrants"]}
        for h in original:
            n = int(h["startNumber"])
            horse_reasons = list(reasons)
            source = next((x for x in field if x["number"] == n), None)
            parsed = biography(pdf.get(n, {}).get("identity_text", ""))
            if not parsed or not source:
                horse_reasons.append("BIOGRAPHY_MISSING")
            else:
                horse = source["horse"]
                pedigree = horse.get("pedigree", {})
                corroboration = (horse.get("age"), horse.get("sex"),
                    name_key(pedigree.get("father", {}).get("name", "")),
                    name_key(pedigree.get("mother", {}).get("name", "")))
                if parsed != corroboration or name_key(pdf[n]["name"]) != name_key(h["horseName"]):
                    horse_reasons.append("BIOGRAPHY_CONFLICT")
                if not isinstance(horse.get("id"), int) or isinstance(horse.get("id"), bool) or horse["id"] <= 0:
                    horse_reasons.append("STABLE_ID_MISSING")
                if not h["horseRegistrationNumber"].startswith("TMP-"):
                    horse_reasons.append("EXISTING_REGISTRATION_REQUIRES_CROSS_NAMESPACE_REVIEW")
            links.append({"raceday_key": mid, "race_number": number, "selection_id": str(n),
                "name": h["horseName"], "original_registration": h["horseRegistrationNumber"],
                "status": "IDENTITY_VERIFIED" if not horse_reasons else "UNRESOLVED",
                "provider_identity": {"namespace": "ATG_HORSE", "id": str(source["horse"]["id"])} if not horse_reasons else None,
                "reasons": horse_reasons, "biography": parsed,
                "proof": {"program_archive_sha256": archive.sha256,
                    "starts": archive.source(starts_member), "program": archive.source("structured_program_day.json"),
                    "program_pointer": f"/races/{doc_index}/entrants/" + str(next((i for i, x in enumerate(doc["entrants"]) if x["program_number"] == n), -1)),
                    "atg_archive_sha256": evidence_sha, "atg_member": member,
                    "atg_member_sha256": manifest["files_sha256"].get(member),
                    "atg_pointer": "/payload/races/0/starts/" + str(next((i for i, x in enumerate(field) if x["number"] == n), -1)),
                    "atg_url": envelope["url"] if envelope else None,
                    "observed_at": envelope["observed_at"] if envelope else None,
                    "calendar_member_sha256": manifest["files_sha256"]["calendar.json"]},
                "role": "RETROSPECTIVE_IDENTITY_ONLY", "pre_race_availability_verified": False})
    identities = {}
    for link in links:
        if link["provider_identity"]:
            key = link["provider_identity"]["id"]
            identities.setdefault(key, []).append(link)
    for matches in identities.values():
        if len({(name_key(x["name"]), tuple(x["biography"])) for x in matches}) > 1:
            for link in matches:
                link.update(status="CONFLICT", provider_identity=None, reasons=["CROSS_RACE_BIOGRAPHY_CONFLICT"])
    originals = {}
    for link in links:
        originals.setdefault(link["original_registration"], []).append(link)
    for matches in originals.values():
        ids = {x["provider_identity"]["id"] for x in matches if x["provider_identity"]}
        if len(ids) > 1:
            for link in matches:
                link.update(status="CONFLICT", provider_identity=None, reasons=["ORIGINAL_REGISTRATION_CONFLICT"])
    return {"schema": "HBI_SE_IDENTITY_EVIDENCE_V1", "date": archive.day,
        "races": len({(x["raceday_key"], x["race_number"]) for x in links}), "horses": len(links),
        "original_stable_registrations": sum(not x["original_registration"].startswith("TMP-") for x in links),
        "status_counts": dict(Counter(x["status"] for x in links)), "links": links,
        "provider_admission_changed": False, "model_eligible": 0}


def cli(args):
    try:
        report = resolve(DailyArchive(args.archive, args.sha256, args.date), args.atg_archive, args.atg_sha256)
        with Path(args.output).open("x") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps({k: v for k, v in report.items() if k != "links"}, ensure_ascii=False))
