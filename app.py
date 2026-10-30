import io
import re

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Yorum Duygu Analizi", page_icon="📊", layout="wide")

# Kök tabanlı sözlükler: sözcük bu köklerden biriyle başlıyorsa eşleşir.
POSITIVE = {
    "güzel", "iyi", "mükemmel", "harika", "muhteşem", "başarılı", "memnun", "teşekkür",
    "kolay", "hızlı", "pratik", "kullanışlı", "faydalı", "yararlı", "kaliteli", "süper",
    "sevdi", "beğen", "mutlu", "rahat", "sorunsuz", "düzgün", "etkili", "verimli",
    "olumlu", "tavsiye", "öneri", "çözüm", "net", "anlaşılır", "profesyonel", "ilgili",
    "hoş", "şahane", "bayıl", "sağol", "eyvallah", "tebrik", "kusursuz", "başarı",
}
NEGATIVE = {
    "kötü", "berbat", "rezalet", "yavaş", "sorun", "problem", "hata", "şikayet", "şikâyet",
    "memnuniyetsiz", "zor", "karışık", "karmaşık", "yetersiz", "bozuk", "çöktü", "çöker",
    "donuyor", "donma", "kızgın", "sinir", "mağdur", "olumsuz", "başarısız", "gereksiz",
    "pahalı", "geç", "gecik", "bekle", "ulaşılamıyor", "açılmıyor", "çalışmıyor", "yanlış",
    "eksik", "felaket", "korkunç", "vasat", "sıkıntı", "dert", "hayal kırıklığı", "perişan",
    "kullanışsız", "anlaşılmaz", "çözümsüz", "yazık", "üzücü", "bıktı", "bık",
}
# Kökün ardından gelen olumsuzluk ekleri (-ma/-me) ve ayrı sözcük olumsuzlayıcılar.
NEG_SUFFIX = re.compile(r"^(ma|me|mı|mi|mu|mü)(dı|di|du|dü|yor|z|s|sın|sin|sun|sün|yacak|yecek|m|k)?")
NEGATORS_AFTER = {"değil", "degil", "yok", "değildi", "yoktu", "değildir"}
NEGATORS_BEFORE = {"hiç", "asla", "katiyen", "ne"}
CANDIDATE_ENCODINGS = ["utf-8-sig", "utf-8", "cp1254", "iso-8859-9", "cp1252", "latin-1"]


def tr_lower(text: str) -> str:
    return text.replace("İ", "i").replace("I", "ı").lower()


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zçğıöşüâîû]+", tr_lower(text))


def match_stem(token: str, stems: set[str]):
    """Eşleşen kök varsa (kök, kalan ek) döndürür; en uzun kök tercih edilir."""
    best = None
    for stem in stems:
        if " " in stem or len(stem) < 3:
            continue
        if token.startswith(stem) and (best is None or len(stem) > len(best)):
            best = stem
    return (best, token[len(best):]) if best else None


def analyze_text(text) -> tuple[str, int]:
    """(etiket, skor) döndürür. Boş/eksik metin 'Boş' olarak işaretlenir."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return "Boş", 0
    text = str(text).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return "Boş", 0

    tokens = tokenize(text)
    score = 0
    for i, tok in enumerate(tokens):
        polarity = 0
        pos = match_stem(tok, POSITIVE)
        neg = match_stem(tok, NEGATIVE)
        if pos and (not neg or len(pos[0]) >= len(neg[0])):
            polarity, rest = 1, pos[1]
        elif neg:
            polarity, rest = -1, neg[1]
        else:
            continue
        # Kök içindeki "sız/siz" olumsuz kelimeler zaten sözlükte; ek olumsuzluğu çevirir.
        if NEG_SUFFIX.match(rest):
            polarity = -polarity
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        prev = tokens[i - 1] if i > 0 else ""
        if nxt in NEGATORS_AFTER or prev in NEGATORS_BEFORE:
            polarity = -polarity
        score += polarity

    # "değil/yok" gibi tek başına kalan olumsuzlamalar için "yok" ile biten ifadeler.
    if score > 0:
        return "Olumlu", score
    if score < 0:
        return "Olumsuz", score
    return "Nötr", 0


def read_csv_bytes(raw: bytes) -> pd.DataFrame:
    last_err = None
    for enc in CANDIDATE_ENCODINGS:
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError as e:
            last_err = e
            continue
        try:
            return pd.read_csv(io.StringIO(text), sep=None, engine="python", dtype=str)
        except Exception as e:  # ayraç/biçim hatası
            last_err = e
    raise ValueError(f"CSV okunamadı: {last_err}")


@st.cache_data(show_spinner=False)
def load_file(name: str, raw: bytes) -> pd.DataFrame:
    if name.lower().endswith((".xlsx", ".xlsm")):
        return pd.read_excel(io.BytesIO(raw), engine="openpyxl", dtype=str)
    return read_csv_bytes(raw)


st.title("📊 Yorum Duygu Analizi")
st.warning(
    "Bu analiz, Türkçe olumlu/olumsuz sözcük listeleri ve olumsuzlama kurallarına dayalı "
    "**kural tabanlı** bir yöntemdir. Ironi, deyim ve bağlam gibi durumlarda **hata yapabilir**; "
    "sonuçlar kesin kabul edilmemelidir."
)

uploaded = st.file_uploader("CSV veya Excel (.xlsx) dosyası yükleyin", type=["csv", "xlsx", "xlsm"])

if uploaded is None:
    st.info("Başlamak için yorumları içeren bir dosya yükleyin.")
    st.stop()

try:
    df = load_file(uploaded.name, uploaded.getvalue())
except Exception as e:
    st.error(f"Dosya okunamadı: {e}")
    st.stop()

if df.empty or len(df.columns) == 0:
    st.error("Dosyada veri bulunamadı.")
    st.stop()

df.columns = [str(c).strip() for c in df.columns]
col = st.selectbox("Yorum sütunu", list(df.columns))

result = df.copy()
analysis = result[col].map(analyze_text)
result["Duygu"] = analysis.map(lambda x: x[0])
result["Skor"] = analysis.map(lambda x: x[1])

total = len(result)
empty = int((result["Duygu"] == "Boş").sum())
valid = result[result["Duygu"] != "Boş"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Toplam satır", total)
c2.metric("Olumlu", int((result["Duygu"] == "Olumlu").sum()))
c3.metric("Olumsuz", int((result["Duygu"] == "Olumsuz").sum()))
c4.metric("Boş / Nötr", f"{empty} / {int((result['Duygu'] == 'Nötr').sum())}")

if valid.empty:
    st.warning("Seçili sütunda analiz edilebilir yorum yok.")
else:
    counts = valid["Duygu"].value_counts().reset_index()
    counts.columns = ["Duygu", "Adet"]
    colors = {"Olumlu": "#2e9e5b", "Olumsuz": "#d64545", "Nötr": "#8a8f98"}
    left, right = st.columns(2)
    left.plotly_chart(
        px.pie(counts, names="Duygu", values="Adet", color="Duygu", color_discrete_map=colors,
               title="Duygu dağılımı"),
        use_container_width=True,
    )
    right.plotly_chart(
        px.bar(counts, x="Duygu", y="Adet", color="Duygu", color_discrete_map=colors,
               title="Duygu sayıları"),
        use_container_width=True,
    )

filt = st.multiselect("Duyguya göre filtrele", ["Olumlu", "Olumsuz", "Nötr", "Boş"],
                      default=["Olumlu", "Olumsuz", "Nötr", "Boş"])
shown = result[result["Duygu"].isin(filt)]
st.dataframe(shown, use_container_width=True)

csv_bytes = shown.to_csv(index=False).encode("utf-8-sig")
xlsx_buf = io.BytesIO()
shown.to_excel(xlsx_buf, index=False, engine="openpyxl")
d1, d2 = st.columns(2)
d1.download_button("CSV indir", csv_bytes, "analiz_sonuc.csv", "text/csv")
d2.download_button(
    "Excel indir", xlsx_buf.getvalue(), "analiz_sonuc.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
