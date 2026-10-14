#!/usr/bin/env python3
"""Writes the English + Indian language pairs into agent-runner's src/prompts/system_one.json.

Every option quotes real examples with their English meaning: sentences of that language with a few English words in its
own letters, and English as our speech-to-text writes it when locked to that language. The rule names common English words
in that script. Examples come from contrast.json (written and reviewed) and stt_english_indian.json (Deepgram's own lines).

    python3 make_pairs_en.py <system_one.json> [--no-glossary]
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
ENGLISH = "I don't have time right now, please call me in the evening"
NAMES = {"hi": ("Hindi", "Hindi"), "mr": ("Marathi", "Devanagari"), "ta": ("Tamil", "Tamil"), "te": ("Telugu", "Telugu"),
         "kn": ("Kannada", "Kannada"), "bn": ("Bengali", "Bengali"), "gu": ("Gujarati", "Gujarati"), "ml": ("Malayalam", "Malayalam"),
         "pa": ("Punjabi", "Gurmukhi"), "or": ("Odia", "Odia")}
NATIVE = {  # "I don't have time right now, call me in the evening", in the language's own words and letters
    "hi": "मेरे पास अभी समय नहीं है, शाम को फ़ोन कीजिए", "mr": "मला आता वेळ नाही, संध्याकाळी फोन करा",
    "ta": "எனக்கு இப்போ நேரம் இல்லை, சாயங்காலம் போன் பண்ணுங்க", "te": "నాకు ఇప్పుడు సమయం లేదు, సాయంత్రం ఫోన్ చేయండి",
    "kn": "ನನಗೆ ಈಗ ಸಮಯ ಇಲ್ಲ, ಸಂಜೆ ಫೋನ್ ಮಾಡಿ", "bn": "আমার এখন সময় নেই, সন্ধ্যায় ফোন করুন",
    "gu": "મારી પાસે અત્યારે સમય નથી, સાંજે ફોન કરજો", "ml": "എനിക്ക് ഇപ്പോൾ സമയമില്ല, വൈകുന്നേരം ഫോൺ ചെയ്യൂ",
    "pa": "ਮੇਰੇ ਕੋਲ ਹੁਣ ਸਮਾਂ ਨਹੀਂ ਹੈ, ਸ਼ਾਮ ਨੂੰ ਫ਼ੋਨ ਕਰੋ", "or": "ମୋ ପାଖରେ ଏବେ ସମୟ ନାହିଁ, ସନ୍ଧ୍ୟାରେ ଫୋନ କରନ୍ତୁ",
}
# English as the speech-to-text writes it in each script: "please send me the invoice by email", "I am the account holder"
ENGLISH_IN = {
    "hi": ["सेंड मी द इन्वॉइस बाय ईमेल", "आय एम द अकाउंट होल्डर"], "mr": ["सेंड मी द इन्वॉइज बाय ईमेल", "आय एम द अकाउंट होल्डर"],
    "ta": ["ப்ளீஸ் சென்ட் மீ தி இன்வைஸ் பை ஈமெயில்", "எஸ் ஐ அம் தி அக்கவுண்ட் ஹோல்டர்"],
    "te": ["ప్లీజ్ సెండ్ మీ ది ఇన్వాయిస్ బై ఈమెయిల్", "ఐ యామ్ ది అకౌంట్ హోల్డర్"],
    "kn": ["ಪ್ಲೀಸ್ ಸೆಂಡ್ ಮೀ ದಿ ಇನ್ವಾಯ್ಸ್ ಬೈ ಇಮೇಲ್", "ಐ ಆಮ್ ದಿ ಅಕೌಂಟ್ ಹೋಲ್ಡರ್"],
    "bn": ["প্লিজ সেন্ড মি দি ইনভয়েস বাই ইমেইল", "আই এম দি অ্যাকাউন্ট হোল্ডার"],
    "gu": ["પ્લીઝ સેન્ડ મી ધ ઇનવોઇસ બાય ઇમેઇલ", "આઈ એમ ધી એકાઉન્ટ હોલ્ડર"],
    "ml": ["പ്ലീസ് സെൻഡ് മീ ദി ഇൻവോയ്സ് ബൈ ഇമെയിൽ", "ഐ ആം ദി അക്കൗണ്ട് ഹോൾഡർ"],
    "pa": ["ਪਲੀਜ਼ ਸੈਂਡ ਮੀ ਦ ਇਨਵੌਇਸ ਬਾਏ ਈਮੇਲ", "ਆਈ ਐਮ ਦ ਅਕਾਊਂਟ ਹੋਲਡਰ"],
    "or": ["ପ୍ଲିଜ୍ ସେଣ୍ଡ ମି ଦି ଇନଭଏସ ବାଇ ଇମେଲ", "ଆଇ ଆମ ଦି ଆକାଉଣ୍ଟ ହୋଲ୍ଡର"],
}
ENGLISH_MEANING = ["please send me the invoice by email", "I am the account holder"]
GLOSSED = ("my", "order", "please", "check", "call", "payment", "yes", "okay", "sorry", "time")


def pair(code: str, contrast: dict, glossary: bool) -> dict:
    name, letters = NAMES[code]
    mixed = contrast[code]["prompt"]  # two sentences of the language with a few English words, with their meaning
    words = contrast[code]["glossary"]
    listed = ", ".join(f"{words[w]} (\"{w}\")" for w in GLOSSED if w in words)
    script = "Hindi letters" if code == "hi" else f"{name} letters"
    rule = (f"Count each word by the language it comes from, not by the letters it is written in. {name} typed in English letters "
            f"is {name}, and an English word written in {script} is English")
    rule += f": the caller's English words often come written in {script}, such as {listed}." if glossary else "."
    first, second = ENGLISH_IN[code]
    return {
        "rule": rule,
        "English": (f"More than half of the words are English, in English letters or in {script}, such as \"{ENGLISH}\", "
                    f"\"{first}\" (\"{ENGLISH_MEANING[0]}\") or \"{second}\" (\"{ENGLISH_MEANING[1]}\"). "
                    f"Not \"{mixed[0]['text']}\" (\"{mixed[0]['meaning']}\"), which is {name} with a few English words."),
        name: (f"More than half of the words are {name}, in {script} or in English letters, such as \"{NATIVE[code]}\", "
               f"\"{mixed[0]['text']}\" (\"{mixed[0]['meaning']}\") or \"{mixed[1]['text']}\" (\"{mixed[1]['meaning']}\"), "
               f"where {name} words carry a few English ones. Not \"{second}\" (\"{ENGLISH_MEANING[1]}\"), which is English written in {script}."),
    }


def main(path: str, glossary: bool) -> None:
    contrast = json.loads((HERE / "contrast.json").read_text(encoding="utf-8"))
    raw = json.load(open(path, encoding="utf-8"))
    out = {}
    for key, value in raw.items():
        if key == "language":
            value = {**value, "instructions": value["instructions"].replace(
                "Hindi typed in English letters is Hindi, and an English word written in Hindi letters is English.", "{rule}"),
                "criteria": {"Unsure": value["criteria"]["Unsure"]}}
            assert "{rule}" in value["instructions"]
            out[key] = value
            out["language_pairs"] = {f"en+{code}": pair(code, contrast, glossary) for code in NAMES}
            continue
        if key == "reply_in":
            for code, (name, letters) in NAMES.items():
                value.setdefault(name, f"The caller's last sentence was in {name}. Say this whole turn in {name}, in {letters} letters, keeping "
                                       "common English words such as names, brands and app words in English, whatever language the call was in before.")
        out[key] = value
    open(path, "w", encoding="utf-8").write(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(len(out["language_pairs"]), "pairs,", len(out["reply_in"]), "reply notes")


if __name__ == "__main__":
    main(sys.argv[1], "--no-glossary" not in sys.argv)
