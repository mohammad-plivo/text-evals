"""Held-out caller sentences for the language bench: none of them is an example in the prompt.

Per language, five meanings in its own letters and in English letters, and one with an English word mixed in:
yes I am speaking / my order has not come yet / I will pay on Friday / send me the details on WhatsApp / who is calling.
"""
LANGUAGES = {
    "hi": ["हाँ, मैं बोल रहा हूँ", "haan, main bol raha hoon", "मेरा ऑर्डर अभी तक नहीं आया", "mera order abhi tak nahi aaya",
           "मैं शुक्रवार को पैसे दे दूँगा", "main shukravaar ko paise de dunga", "डिटेल्स मुझे व्हाट्सऐप पर भेज दीजिए",
           "details mujhe WhatsApp pe bhej dijiye", "कौन बोल रहा है?", "kaun bol raha hai?", "payment kal tak ho jayega"],
    "mr": ["हो, मी बोलतोय", "ho, mi boltoy", "माझी ऑर्डर अजून आली नाही", "majhi order ajun aali nahi", "मी शुक्रवारी पैसे भरतो",
           "mi shukravari paise bharto", "मला डिटेल्स व्हॉट्सअॅपवर पाठवा", "mala details WhatsApp var pathva", "कोण बोलतंय?",
           "kon boltay?", "payment udya paryant hoil"],
    "ta": ["ஆமா, நான் தான் பேசுறேன்", "aama, naan thaan pesuren", "என் ஆர்டர் இன்னும் வரலை", "en order innum varala",
           "நான் வெள்ளிக்கிழமை பணம் கட்டுறேன்", "naan velli kizhamai panam katturen", "எனக்கு டீடெயில்ஸ் வாட்ஸ்அப்ல அனுப்புங்க",
           "enakku details WhatsApp la anuppunga", "யாரு பேசுறது?", "yaaru pesurathu?", "payment naalaikku pannuren"],
    "te": ["అవును, నేనే మాట్లాడుతున్నాను", "avunu, nene maatlaadutunnaanu", "నా ఆర్డర్ ఇంకా రాలేదు", "naa order inka raaledu",
           "నేను శుక్రవారం డబ్బులు కడతాను", "nenu shukravaaram dabbulu kadataanu", "నాకు డీటెయిల్స్ వాట్సాప్ లో పంపండి",
           "naaku details WhatsApp lo pampandi", "ఎవరు మాట్లాడుతున్నారు?", "evaru maatlaadutunnaaru?", "payment repu chestanu"],
    "kn": ["ಹೌದು, ನಾನೇ ಮಾತಾಡ್ತಿದ್ದೀನಿ", "houdu, naane maataadtiddini", "ನನ್ನ ಆರ್ಡರ್ ಇನ್ನೂ ಬಂದಿಲ್ಲ", "nanna order innu bandilla",
           "ನಾನು ಶುಕ್ರವಾರ ದುಡ್ಡು ಕಟ್ತೀನಿ", "naanu shukravaara duddu kattini", "ನನಗೆ ಡೀಟೇಲ್ಸ್ ವಾಟ್ಸಾಪ್ ಅಲ್ಲಿ ಕಳಿಸಿ",
           "nanage details WhatsApp alli kalisi", "ಯಾರು ಮಾತಾಡ್ತಿರೋದು?", "yaaru maataadtirodu?", "payment naale maadtini"],
    "bn": ["হ্যাঁ, আমি বলছি", "hyan, ami bolchhi", "আমার অর্ডার এখনও আসেনি", "amar order ekhono ashe ni", "আমি শুক্রবার টাকা দিয়ে দেব",
           "ami shukrobar taka diye debo", "আমাকে ডিটেলস হোয়াটসঅ্যাপে পাঠিয়ে দিন", "amake details WhatsApp e pathiye din", "কে বলছেন?",
           "ke bolchhen?", "payment kal kore debo"],
    "gu": ["હા, હું બોલું છું", "ha, hu bolu chhu", "મારો ઓર્ડર હજુ આવ્યો નથી", "maro order haju aavyo nathi", "હું શુક્રવારે પૈસા ભરી દઈશ",
           "hu shukravaare paisa bhari daish", "મને ડિટેલ્સ વોટ્સએપ પર મોકલો", "mane details WhatsApp par moklo", "કોણ બોલે છે?",
           "kon bole chhe?", "payment kaale kari daish"],
    "ml": ["അതെ, ഞാനാണ് സംസാരിക്കുന്നത്", "athe, njaanaanu samsaarikkunnathu", "എന്റെ ഓർഡർ ഇതുവരെ വന്നില്ല", "ente order ithuvare vannilla",
           "ഞാൻ വെള്ളിയാഴ്ച പണം അടയ്ക്കാം", "njaan velliyaazhcha panam adaykkaam", "എനിക്ക് ഡീറ്റെയിൽസ് വാട്സ്ആപ്പിൽ അയയ്ക്കൂ",
           "enikku details WhatsApp il ayakku", "ആരാണ് സംസാരിക്കുന്നത്?", "aaraanu samsaarikkunnathu?", "payment naale cheyyaam"],
    "pa": ["ਹਾਂ ਜੀ, ਮੈਂ ਬੋਲ ਰਿਹਾ ਹਾਂ", "haan ji, main bol reha haan", "ਮੇਰਾ ਆਰਡਰ ਅਜੇ ਤੱਕ ਨਹੀਂ ਆਇਆ", "mera order aje tak nahi aaya",
           "ਮੈਂ ਸ਼ੁੱਕਰਵਾਰ ਨੂੰ ਪੈਸੇ ਦੇ ਦਿਆਂਗਾ", "main shukarvaar nu paise de diyanga", "ਮੈਨੂੰ ਡੀਟੇਲਾਂ ਵਟਸਐਪ ਤੇ ਭੇਜ ਦਿਓ",
           "mainu details WhatsApp te bhej dio", "ਕੌਣ ਬੋਲ ਰਿਹਾ ਹੈ?", "kaun bol reha hai?", "payment kal tak kar dayanga"],
    "or": ["ହଁ, ମୁଁ କହୁଛି", "han, mun kahuchhi", "ମୋ ଅର୍ଡର ଏଯାଏଁ ଆସିନାହିଁ", "mo order ejaye asinahin", "ମୁଁ ଶୁକ୍ରବାର ଟଙ୍କା ଦେଇଦେବି",
           "mun sukrabara tanka deidebi", "ମୋତେ ଡିଟେଲ୍ସ ହ୍ୱାଟସଆପରେ ପଠାନ୍ତୁ", "mote details WhatsApp re pathantu", "କିଏ କହୁଛନ୍ତି?",
           "kie kahuchhanti?", "payment kali kari debi"],
}
NAMES = {"hi": "Hindi", "mr": "Marathi", "ta": "Tamil", "te": "Telugu", "kn": "Kannada", "bn": "Bengali", "gu": "Gujarati",
         "ml": "Malayalam", "pa": "Punjabi", "or": "Odia"}
ENGLISH = ["Yes, this is him speaking.", "My order still hasn't arrived.", "I'll make the payment on Friday.",
           "Can you send the details on WhatsApp?", "Who is this?"]
NEUTRAL = ["Ramesh Kumar", "9876543214", "hmm"]  # a name, a number, a sound: no language to judge
# what a speech-to-text pinned to the other language writes: English, and Hindi, in that language's letters
ENGLISH_IN = {  # "My order still hasn't arrived." / "Who is this?"
    "hi": ["माय ऑर्डर स्टिल हैज़न्ट अराइव्ड", "हू इज़ दिस?"], "mr": ["माय ऑर्डर स्टिल हॅजन्ट अराइव्ड", "हू इज धिस?"],
    "ta": ["மை ஆர்டர் ஸ்டில் ஹேஸன்ட் அரைவ்டு", "ஹூ இஸ் திஸ்?"], "te": ["మై ఆర్డర్ స్టిల్ హాజంట్ అరైవ్డ్", "హూ ఈజ్ దిస్?"],
    "kn": ["ಮೈ ಆರ್ಡರ್ ಸ್ಟಿಲ್ ಹ್ಯಾಸಂಟ್ ಅರೈವ್ಡ್", "ಹೂ ಈಸ್ ದಿಸ್?"], "bn": ["মাই অর্ডার স্টিল হ্যাজন্ট অ্যারাইভড", "হু ইজ দিস?"],
    "gu": ["માય ઓર્ડર સ્ટિલ હેઝન્ટ અરાઇવ્ડ", "હુ ઇઝ ધીસ?"], "ml": ["മൈ ഓർഡർ സ്റ്റിൽ ഹാസന്റ് അറൈവ്ഡ്", "ഹൂ ഈസ് ദിസ്?"],
    "pa": ["ਮਾਈ ਆਰਡਰ ਸਟਿਲ ਹੈਜ਼ੰਟ ਅਰਾਈਵਡ", "ਹੂ ਇਜ਼ ਦਿਸ?"], "or": ["ମାଇ ଅର୍ଡର ଷ୍ଟିଲ ହାଜଣ୍ଟ ଆରାଇଭଡ", "ହୁ ଇଜ ଦିସ?"],
}
HINDI_IN = {  # "mera order abhi tak nahi aaya" / "kaun bol raha hai?"
    "ta": ["மேரா ஆர்டர் அபி தக் நஹீ ஆயா", "கௌன் போல் ரஹா ஹை?"], "te": ["మేరా ఆర్డర్ అభీ తక్ నహీ ఆయా", "కౌన్ బోల్ రహా హై?"],
    "kn": ["ಮೇರಾ ಆರ್ಡರ್ ಅಭೀ ತಕ್ ನಹೀ ಆಯಾ", "ಕೌನ್ ಬೋಲ್ ರಹಾ ಹೈ?"], "bn": ["মেরা অর্ডার অভি তক নহী আয়া", "কৌন বোল রহা হৈ?"],
    "gu": ["મેરા ઓર્ડર અભી તક નહીં આયા", "કૌન બોલ રહા હૈ?"], "ml": ["മേരാ ഓർഡർ അഭീ തക് നഹീ ആയാ", "കൗൻ ബോൽ രഹാ ഹൈ?"],
    "pa": ["ਮੇਰਾ ਆਰਡਰ ਅਭੀ ਤਕ ਨਹੀਂ ਆਯਾ", "ਕੌਣ ਬੋਲ ਰਹਾ ਹੈ?"], "or": ["ମେରା ଅର୍ଡର ଅଭୀ ତକ ନହୀଁ ଆୟା", "କୌନ ବୋଲ ରହା ହୈ?"],
}


def cases(pair: str) -> list[tuple[str, str]]:
    """(sentence, the reading expected) for one pair; Unsure for words of neither language."""
    first, second = pair.split("+")
    out = [(line, NAMES[second]) for line in LANGUAGES[second]]
    if first == "en":
        out += [(line, "English") for line in ENGLISH + ENGLISH_IN[second]]
    else:
        out += [(line, "Hindi") for line in LANGUAGES["hi"] + HINDI_IN.get(second, [])] + [(line, "Unsure") for line in ENGLISH[1::3]]
    return out + [(line, "Unsure") for line in NEUTRAL]
