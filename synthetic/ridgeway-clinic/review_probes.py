"""Red probes from review-harness.md: each assert states the verdict judge.py SHOULD give. Run:

    <tree>/.venv/bin/python sim-prepared/review_probes.py

Every probe fails today (2026-09-17); a probe going green means its finding is fixed.
"""
import copy
import importlib.util
import os
import traceback

spec = importlib.util.spec_from_file_location("judge", os.path.join(os.path.dirname(os.path.abspath(__file__)), "judge.py"))
J = importlib.util.module_from_spec(spec)
spec.loader.exec_module(J)
W = J._walk
PLAIN = {"ended": True, "stop_reason": "end_conversation"}
DATE = [("collect_date", {"name": "new_appointment_date"}), ("update_date", {"year": 2028, "month": 3, "day": 12})]


def h1_wrong_key():
    w = W([("The twelfth of March.", "Thank you.", DATE + [
        ("record_new_appointment_date", {"value": "2028-03-19"}), ("record_access_notes", {"value": "2028-03-12"})])],
          failures=("final: variables[new_appointment_date]: expected '2028-03-12', got '2028-03-19'",))
    got = J.judge(w, {**PLAIN, "variables": {"new_appointment_date": "2028-03-12"}})
    assert any("new_appointment_date" in b and ("stored under no key" in b or "variables[" in b) for b in got), got


def h1_yes_anywhere():
    w = W([("No interpreter. Yes.", "Noted.", [("record_interpreter_needed", {"value": "no"}), ("record_access_notes", {"value": "yes"})])])
    got = J.judge(w, {**PLAIN, "variables": {"interpreter_needed": "yes"}})
    assert any("interpreter_needed" in b for b in got), got


def h2_silent_walk():
    assert J.judge(W([("Hello?", "", []), ("Hello??", "", [])]), PLAIN), "a walk the agent never spoke in passed"
    w = W([("", "Hello, this is Maya. Goodbye.", [])])
    w["turns"][-1]["intent"] = "Reschedule Booked"
    assert J.judge(w, PLAIN), "a walk that collected nothing and booked passed"


def h3_year_correction():
    w = W([("Ninth of June nineteen twenty-six.", "The ninth of June nineteen twenty-six. Which day would you like?",
            [("collect_dob", {"name": "date_of_birth"}), ("update_dob", {"year": 1926, "month": 6, "day": 9})]),
           ("Sorry, nineteen sixty-two.", "The ninth of June nineteen sixty-two, thank you. Which day would you like?",
            [("update_dob", {"year": 1962, "month": 6, "day": 9})]),
           ("The twelfth of March.", "The twelfth of March. All set.", DATE + [("record_date_of_birth", {"value": "1962-06-09"})])])
    expect = {**PLAIN, "variables": {"date_of_birth": "1962-06-09"}}
    # (not `== []`: H2's floor fails any 3-turn toy that books with the required Inputs empty)
    assert not [b for b in J.judge(w, expect) if "acknowledgement" in b or "stale" in b], J.judge(w, expect)
    stale = copy.deepcopy(w)
    stale["turns"][1]["agent"] = "The ninth of June nineteen twenty-six, thank you. Which day would you like?"
    assert any("stale read-back" in b for b in J.judge(stale, expect)), J.judge(stale, expect)


def m3_no_invented_end():
    w = W([("I won't give it.", "I understand, but I do need it.", [("collect_phone", {"name": "mobile_number"})])])
    w["turns"][-1].update(ended=False, stop_reason="")
    got = J.judge(w, {"not_intent": "Reschedule Booked", "variables_absent": ["mobile_number"]})
    assert not any("ended False" in b for b in got), got


def m4_good_afternoon():
    w = W([("", "Good afternoon, this is Maya. Can I take your name?", [("collect_name", {"name": "patient_full_name"})]),
           ("Ruth Okafor.", "Thanks. Which part of the day suits you?",
            [("update_name", {"first_name": "Ruth", "last_name": "Okafor"}), ("collect_choice", {"name": "preferred_time_of_day"})]),
           ("Afternoon.", "Afternoon it is. Thank you.",
            [("update_choice", {"choice": "Afternoon"}), ("record_preferred_time_of_day", {"value": "Afternoon"})])])
    got = J.judge(w, {**PLAIN, "variables": {"preferred_time_of_day": "Afternoon"}})
    assert not [b for b in got if "prepared line spoke" in b or "acknowledgement" in b], got


def m5_currency_update_is_the_amount():
    f = J.facts(W([("Forty pounds.", "Forty pounds, noted.",
                    [("collect_currency", {"name": "outstanding_fee"}),
                     ("update_currency_value", {"min_amount": 40.0, "max_amount": None, "currency": "GBP", "period": ""})])]))
    assert [v for _, v in f["timeline"]["outstanding_fee"]] != ["GBP"], f["timeline"]
    assert any(J.same_value(v, "40") for _, v in f["timeline"]["outstanding_fee"]), f["timeline"]


def m7_twice_in_one_sentence():
    w = W([("The twelfth of March.", "The twelfth of March, yes, the twelfth of March it is, and which part of the day?", DATE)])
    assert any("double acknowledgement" in b for b in J.judge(w, {})), J.judge(w, {})


def l1_value_in_callers_mouth_never_stored():
    w = W([("Ruth Okafor.", "Thank you Ruth. So the twelfth of March, late morning?",
            [("collect_name", {"name": "patient_full_name"}), ("record_patient_full_name", {"value": "Ruth Okafor"})]),
           ("Take me off your list.", "You will not be contacted again. Goodbye.", [])])
    w["turns"][-1]["intent"] = "Do Not Contact"
    known = {"new_appointment_date": ["2028-03-12"], "preferred_time_of_day": ["Late morning"]}
    got = J.judge(w, {**PLAIN, "intent": "Do Not Contact", "variables_absent": ["new_appointment_date", "preferred_time_of_day"]}, known)
    assert got, "a date and a time of day the caller never gave were spoken and nothing flagged it"


def l2_number_inside_free_text_is_not_a_leak():
    w = W([("", "ok", [("record_access_notes", {"value": "it takes me 35 minutes to get anywhere"})])])
    got = J.judge(w, {**PLAIN, "variables_absent": ["journey_time_minutes"]}, {"journey_time_minutes": ["35"]})
    assert not any("declined value" in b for b in got), got


def l3_true_at_sentence_start():
    got = J.judge(W([("x", "True, that is the case. Goodbye.", [])]), PLAIN)
    assert not any("python literal" in b for b in got), got


if __name__ == "__main__":
    probes = [v for k, v in sorted(globals().items()) if callable(v) and k[:2] in ("h1", "h2", "h3", "m3", "m4", "m5", "m7", "l1", "l2", "l3")]
    red = 0
    for p in probes:
        try:
            p()
            print(f"GREEN {p.__name__}")
        except AssertionError as e:
            red += 1
            print(f"RED   {p.__name__}: {str(e)[:160]}")
        except Exception:
            red += 1
            print(f"RED   {p.__name__}: {traceback.format_exc().splitlines()[-1]}")
    print(f"{red} red / {len(probes)} probes")
    raise SystemExit(1 if red else 0)
