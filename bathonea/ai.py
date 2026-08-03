"""DeepSeek API üzerinden, yalnızca yüklenen belgeye dayanarak soru cevaplama."""
import re
import requests

DEEPSEEK_URL = 'https://api.deepseek.com/chat/completions'
MAX_CONTEXT_CHARS = 55000  # yaklaşık DeepSeek bağlam sınırının altında güvenli pay

SYSTEM_PROMPT = (
    "Sen Bathonea Yapı A.Ş. ile Belediye-İş Sendikası arasındaki Toplu İş Sözleşmesi "
    "hakkında soruları cevaplayan bir asistansın. Sana verilen BELGE METNİ dışında hiçbir "
    "bilgi kullanma, tahmin yürütme veya genel bilgiyle cevap verme. Sadece belgede yazanları "
    "esas al. Eğer sorunun cevabı belgede yoksa, açıkça 'Bu bilgi sözleşme metninde bulunmamaktadır.' "
    "de. Cevaplarını kısa, net ve Türkçe ver. Mümkünse ilgili madde numarasını belirt."
)


def _select_relevant_chunks(pages, question, max_chars):
    """Belge çok uzunsa, soruyla anahtar kelime örtüşmesi en yüksek sayfaları seç."""
    q_words = set(re.findall(r'\w+', question.lower()))
    scored = []
    for p in pages:
        text = p.get('text') or ''
        words = set(re.findall(r'\w+', text.lower()))
        score = len(q_words & words)
        scored.append((score, p['page_number'], text))
    scored.sort(key=lambda x: (-x[0], x[1]))

    chunks = []
    total = 0
    # Puanı olanları önce al
    for score, page_num, text in scored:
        if score <= 0:
            continue
        piece = f"[Sayfa {page_num}]\n{text}\n"
        if total + len(piece) > max_chars:
            continue
        chunks.append(piece)
        total += len(piece)
    if not chunks:
        # Hiçbir eşleşme yoksa baştan itibaren sığdığı kadar al
        for score, page_num, text in sorted(scored, key=lambda x: x[1]):
            piece = f"[Sayfa {page_num}]\n{text}\n"
            if total + len(piece) > max_chars:
                break
            chunks.append(piece)
            total += len(piece)
    return '\n'.join(chunks)


def build_context(pages, question):
    full_text = '\n'.join(f"[Sayfa {p['page_number']}]\n{p.get('text') or ''}\n" for p in pages)
    if len(full_text) <= MAX_CONTEXT_CHARS:
        return full_text
    return _select_relevant_chunks(pages, question, MAX_CONTEXT_CHARS)


class AIError(Exception):
    pass


def ask(question, context_text, api_key, model='deepseek-chat', history=None):
    if not api_key:
        raise AIError('DeepSeek API anahtarı ayarlanmamış. Ayarlar bölümünden ekleyin.')

    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT + '\n\n--- BELGE METNİ ---\n' + context_text},
    ]
    for h in (history or [])[-6:]:
        messages.append({'role': h['role'], 'content': h['text']})
    messages.append({'role': 'user', 'content': question})

    try:
        res = requests.post(
            DEEPSEEK_URL,
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={'model': model, 'messages': messages, 'temperature': 0.2, 'max_tokens': 1000},
            timeout=45,
        )
    except requests.RequestException as e:
        raise AIError(f'DeepSeek bağlantı hatası: {e}')

    if res.status_code != 200:
        raise AIError(f'DeepSeek API hatası ({res.status_code}): {res.text[:300]}')

    data = res.json()
    try:
        return data['choices'][0]['message']['content'].strip()
    except (KeyError, IndexError):
        raise AIError('DeepSeek yanıtı beklenmeyen formatta.')
