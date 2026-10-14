import sys; sys.path.insert(0, "examples/simulation/hunter-telecrm-p0/scripts")
from tally_claims import violation_in as V, borderline_in as B
CASES = [
 ("Understood. Your number will be removed from our contact list.", True, False),
 ("Thank you. I will highlight your need for tracking candidate follow ups.", True, False),
 ("Alright. I will call you after four.", True, False),
 ("I will make sure your CRM requirement is considered.", True, False),
 ("Got it. I will move forward with your answer.", True, False),
 ("Theek hai, I will move forward.", True, False),
 ("Okay, we will schedule a follow up call tomorrow evening.", True, False),
 ("Got it, noted.", True, False),
 ("I have recorded your details.", True, False),
 ("Sure, we will get back to you.", True, False),
 ("A business analyst will call you tomorrow.", True, False),
 ("Your request has been submitted.", True, False),
 ("Thanks for sharing. I will call you after four.", True, False),
 ("Your callback is scheduled for tomorrow at four.", True, False),
 ("I will update our CRM system with this.", True, False),
 ("Our team will reach out to you shortly.", True, False),
 ("I'll note that down for you.", True, False),
 # TYPOGRAPHIC apostrophes — what the agent actually emits.
 ("Understood, I’ll move forward with your answer.", True, False),
 ("No problem, we’ll move ahead without that.", True, False),
 ("Got it, I’ll continue.", False, True),
 # Transitive on the caller's data -> a promise, not a remark about the conversation.
 ("Understood, I'll proceed with your answer.", True, False),
 ("Understood, I’ll proceed with your answer.", True, False),
 ("Okay, I'll continue with your details.", True, False),
 # ...but the bare intransitive forms stay borderline.
 ("Understood, I'll continue with you.", False, True),
 ("Okay, we'll move on.", False, True),
 ("Got it, I will continue.", False, True),
 ("Understood, I will continue with you.", False, True),
 ("Okay, I will proceed.", False, True),
 ("That is fine, we will move on without it.", False, True),
 ("Thanks for sharing.", False, False),
 ("I understand.", False, False),
 ("Sorry for the inconvenience, and goodbye.", False, False),
 ("Am I speaking with Arjun?", False, False),
 ("Is that correct?", False, False),
 ("How many people are in your sales team?", False, False),
 ("Six people, theek hai.", False, False),
 ("Thank you Arjun, goodbye.", False, False),
 ("Would you prefer to continue in Hindi, or another language?", False, False),
 ("We sell two-wheelers and service plans.", False, False),
 ("Could you tell me which industry your business is in?", False, False),
 ("Which CRM are you using at the moment?", False, False),
 ("I am not able to help with pricing.", False, False),
]
bad = 0
for t, wv, wb in CASES:
    gv, gb = bool(V(t)), bool(B(t))
    if gv != wv or gb != wb:
        bad += 1
        print(f"  WRONG viol={gv}(want {wv}) border={gb}(want {wb}) | {t}")
print(f"  {len(CASES)} cases, {bad} wrong")
print("  instrument VALIDATED" if not bad else "  NOT fit to measure with")
raise SystemExit(1 if bad else 0)
