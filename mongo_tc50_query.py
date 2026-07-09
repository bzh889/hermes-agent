"""Query MongoDB (mtkpsi2server:27017, DB Project_Info) for TC50 info.

Collections queried:
  - feature_check_in_window: regex TC50 on Project/Soc/Branch
  - proj_status:            regex TC50 on Project/Soc/Chip

Usage:  python mongo_tc50_query.py
Output: mongo_tc50_output.json (same directory)
"""
import json
import os
import subprocess
import sys
import traceback

try:
    from pymongo import MongoClient
except ImportError:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "pymongo"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    from pymongo import MongoClient

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mongo_tc50_output.json")
TC50 = {"$regex": "TC50", "$options": "i"}


def _ser(doc: dict) -> dict:
    """Make a MongoDB document JSON-serialisable."""
    d = dict(doc)
    d["_id"] = str(d["_id"])
    return {k: (v.decode() if isinstance(v, bytes) else v) for k, v in d.items()}


def main() -> None:
    cli = MongoClient("mtkpsi2server:27017", serverSelectionTimeoutMS=10_000)
    cli.admin.command("ping")
    db = cli["Project_Info"]

    fcw_docs = [_ser(d) for d in db["feature_check_in_window"].find({
        "$or": [{"Project": TC50}, {"Soc": TC50}, {"Branch": TC50},
                {"project": TC50}, {"soc": TC50}, {"branch": TC50}],
    })]
    ps_docs = [_ser(d) for d in db["proj_status"].find({
        "$or": [{"Project": TC50}, {"Soc": TC50}, {"Chip": TC50},
                {"project": TC50}, {"chip": TC50}, {"PROJ": TC50}, {"SOC": TC50}],
    })]

    cli.close()

    results = {
        "feature_check_in_window": {"count": len(fcw_docs), "documents": fcw_docs},
        "proj_status":            {"count": len(ps_docs), "documents": ps_docs},
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"OK → {OUT}  (fcw={len(fcw_docs)}, ps={len(ps_docs)})")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        msg = traceback.format_exc()
        with open(OUT, "w", encoding="utf-8") as f:
            f.write(msg)
        print(msg, file=sys.stderr)
        sys.exit(1)
