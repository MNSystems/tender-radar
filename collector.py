import os
import requests
import json

# Конфигурация Supabase
SUPABASE_URL = "https://fjbbvmtfnypaaffkvbzo.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZqYmJ2bXRmbnlwYWFmZmt2YnpvIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc5MDI3ODc1NiwiZXhwIjoyMTA1ODU0NzU2fQ.jcT0jmIdDj9JRIlM0g6HigDb0lIzXRGJiA0oiWG0rrY")

# Конфигурация Telegram
TELEGRAM_BOT_TOKEN = "8972444318:AAFlm9tqwFDFFh6E8_vkWKfdF4D-vsyQxmMP"

HEADERS_SB = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def get_active_users():
    """Получает всех активных подписчиков и их ключевые слова"""
    url = f"{SUPABASE_URL}/rest/v1/users?select=id,telegram_chat_id,user_keywords(keyword)&is_active=eq.true"
    resp = requests.get(url, headers=HEADERS_SB)
    if resp.status_code == 200:
        return resp.json()
    print("Ошибка загрузки пользователей:", resp.text)
    return []

def get_sent_lots(user_id):
    """Получает список уже отправленных лотов для конкретного клиента"""
    url = f"{SUPABASE_URL}/rest/v1/sent_tenders?select=lot_id&user_id=eq.{user_id}"
    resp = requests.get(url, headers=HEADERS_SB)
    if resp.status_code == 200:
        return {item["lot_id"] for item in resp.json()}
    return set()

def record_sent_lot(lot_id, user_id):
    """Записывает отправленный лот в базу, чтобы не дублировать"""
    url = f"{SUPABASE_URL}/rest/v1/sent_tenders"
    payload = {"lot_id": str(lot_id), "user_id": user_id}
    requests.post(url, headers=HEADERS_SB, json=payload)

def send_telegram_message(chat_id, text):
    """Отправляет карточку тендера в Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    requests.post(url, json=payload)

def fetch_goszakup_lots():
    """Загружает свежие опубликованные лоты с портала Госзакупок РК"""
    # Публичный GraphQL / REST endpoint Госзакупок
    url = "https://ows.goszakup.gov.kz/v3/graphql"
    query = """
    {
      Lots(limit: 50, filter: { lotStatusId: [210, 220] }) {
        id
        lotNumber
        nameRu
        descriptionRu
        amount
        count
        customerNameRu
        TrdBuy {
          id
          nameRu
          publishDate
          endDate
        }
      }
    }
    """
    try:
        resp = requests.post(url, json={"query": query}, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("data", {}).get("Lots", [])
    except Exception as e:
        print("Ошибка подключения к Госзакупкам:", e)
    return []

def main():
    users = get_active_users()
    if not users:
        print("Активных подписчиков не найдено.")
        return

    print(f"Загружено активных клиентов: {len(users)}")
    lots = fetch_goszakup_lots()
    print(f"Получено лотов с портала: {len(lots)}")

    for user in users:
        u_id = user["id"]
        chat_id = user["telegram_chat_id"]
        raw_keywords = [k["keyword"].strip().lower() for k in user.get("user_keywords", [])]
        
        if not raw_keywords:
            continue

        sent_ids = get_sent_lots(u_id)

        for lot in lots:
            lot_id = str(lot.get("id"))
            if lot_id in sent_ids:
                continue

            lot_name = (lot.get("nameRu") or "").lower()
            lot_desc = (lot.get("descriptionRu") or "").lower()
            text_to_search = f"{lot_name} {lot_desc}"

            # Проверка совпадения по ключевым словам клиента
            matched = any(kw in text_to_search for kw in raw_keywords)
            if matched:
                sum_amount = lot.get("amount") or 0
                formatted_sum = f"{float(sum_amount):,.2f} ₸"
                buy = lot.get("TrdBuy") or {}
                buy_id = buy.get("id", "")
                link = f"https://goszakup.gov.kz/ru/announce/index/{buy_id}" if buy_id else "https://goszakup.gov.kz"

                message = (
                    f"🎯 <b>Найден новый тендер по вашим ключевым словам!</b>\n\n"
                    f"📦 <b>Лот:</b> {lot.get('nameRu', 'Без названия')}\n"
                    f"💰 <b>Сумма:</b> {formatted_sum}\n"
                    f"🏢 <b>Заказчик:</b> {lot.get('customerNameRu', 'Не указан')}\n"
                    f"🔗 <a href='{link}'>Открыть на Госзакупках</a>"
                )

                send_telegram_message(chat_id, message)
                record_sent_lot(lot_id, u_id)
                print(f"Отправлен лот {lot_id} пользователю {chat_id}")

if __name__ == "__main__":
    main()
