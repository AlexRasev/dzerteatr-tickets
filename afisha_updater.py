import json
import os
import time
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from collections import defaultdict

# ===== НАСТРОЙКИ =====
TICKETS_FILE = "afisha_data.json"

# ===== ФУНКЦИЯ СОЗДАНИЯ ДРАЙВЕРА =====
def get_driver():
    """Создаёт драйвер Selenium"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=chrome_options)
    return driver

# ===== ПОЛУЧЕНИЕ СПИСКА СЕАНСОВ =====
def get_sessions_from_afisha():
    """Получает список всех сеансов с главной страницы"""
    driver = get_driver()
    try:
        url = "https://quicktickets.ru/dzerjinsk-dramteatr"
        print(f"🔄 Получаем список сеансов с {url}")
        driver.get(url)
        time.sleep(5)

        links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/s']")
        sessions = []
        seen = set()

        for link in links:
            href = link.get_attribute('href')
            if href and '/s' in href:
                match = re.search(r'/s(\d+)', href)
                if match:
                    session_id = match.group(1)
                    if session_id not in seen:
                        seen.add(session_id)
                        title = link.text.strip()
                        if not title:
                            parent = link.find_element(By.XPATH, "..")
                            title = parent.text.strip()
                        sessions.append({
                            'id': int(session_id),
                            'url': href,
                            'title': title
                        })

        print(f"✅ Найдено сеансов: {len(sessions)}")
        driver.quit()
        return sessions
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        driver.quit()
        return []

# ===== ПОЛУЧЕНИЕ НАЗВАНИЯ СПЕКТАКЛЯ СО СТРАНИЦЫ =====
def get_event_name(driver, session_url):
    """
    Получает название спектакля со страницы сеанса.
    Ищет в <h1> или <title>.
    """
    try:
        driver.get(session_url)
        time.sleep(2)

        # Пробуем <h1>
        try:
            h1 = driver.find_element(By.TAG_NAME, "h1")
            name = h1.text.strip()
            if name:
                # Убираем возрастной ценз в конце (например, "Наливные яблочки. 12+")
                name = re.sub(r'\s*\d+\+\s*$', '', name).strip()
                return name
        except:
            pass

        # Пробуем <title>
        try:
            title = driver.title
            if title:
                # "Купить билеты на 03 октября 17:00 «Наливные яблочки.» — ..."
                match = re.search(r'«(.+?)»', title)
                if match:
                    name = match.group(1).strip()
                    # Убираем точку в конце
                    name = name.rstrip('.')
                    return name
        except:
            pass

        return None
    except Exception as e:
        print(f"   ⚠️ Не удалось получить название: {e}")
        return None

# ===== ПАРСИНГ МЕСТ (УНИВЕРСАЛЬНЫЙ) =====
def get_available_places(driver, session_url):
    """Получает количество свободных мест для сеанса"""
    try:
        driver.get(session_url)
        time.sleep(5)

        iframe = driver.find_element(By.TAG_NAME, "iframe")
        driver.switch_to.frame(iframe)

        wait = WebDriverWait(driver, 20)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".hallPlace")))
        time.sleep(2)

        places = driver.find_elements(By.CSS_SELECTOR, ".hallPlace")

        available = 0
        zones = defaultdict(int)

        for place in places:
            label = place.get_attribute("aria-label")
            if label:
                parts = label.split(", ")
                if len(parts) >= 4:
                    status = parts[-1]
                    if status == "доступно":
                        available += 1

                        if parts[0] in ["Партер", "Балкон"]:
                            zone = parts[0]
                        elif any(word in label for word in ["Царевна-лягушка", "Маленький принц", "Аладдин"]):
                            zone = "Партер (детский)"
                        elif len(parts) == 4 and any(c in parts[1] for c in ["А", "Б", "В"]):
                            zone = "Малый зал"
                        else:
                            try:
                                price_str = parts[-2].replace("рублей", "").strip()
                                price = int(price_str)
                                if price <= 500:
                                    zone = "Партер (детский)"
                                elif price >= 1500:
                                    zone = "Малый зал"
                                else:
                                    zone = "Партер"
                            except:
                                zone = "Партер"

                        zones[zone] += 1

        if available > 0 and not zones:
            zones["Партер"] = available

        driver.switch_to.default_content()

        return {
            "available": available,
            "zones": dict(zones),
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return None

# ===== СОРТИРОВКА ПО ДАТЕ =====
def extract_date_from_title(title):
    """Извлекает дату из названия сеанса"""
    if not title:
        return datetime.max

    patterns = [
        r'(\d{2}\s+[а-я]+\s+\d{4})',
        r'(\d{2}\.\d{2}\.\d{4})',
        r'(\d{2}\s+[а-я]+)'
    ]

    for pattern in patterns:
        match = re.search(pattern, title)
        if match:
            date_str = match.group(1)
            try:
                if '.' in date_str:
                    return datetime.strptime(date_str, '%d.%m.%Y')
                else:
                    months = {
                        'января': '01', 'февраля': '02', 'марта': '03',
                        'апреля': '04', 'мая': '05', 'июня': '06',
                        'июля': '07', 'августа': '08', 'сентября': '09',
                        'октября': '10', 'ноября': '11', 'декабря': '12'
                    }
                    for month_ru, month_num in months.items():
                        if month_ru in date_str:
                            day = re.search(r'(\d{2})', date_str).group(1)
                            year = datetime.now().year
                            if int(month_num) < datetime.now().month:
                                year += 1
                            return datetime.strptime(f"{day}.{month_num}.{year}", '%d.%m.%Y')
            except:
                pass
    return datetime.max

# ===== ОСНОВНАЯ ФУНКЦИЯ =====
def update_all_sessions():
    """Обновляет данные для всех сеансов"""
    print("\n" + "=" * 60)
    print("🚀 ОБНОВЛЕНИЕ ДАННЫХ О БИЛЕТАХ")
    print("=" * 60)

    sessions = get_sessions_from_afisha()
    if not sessions:
        print("❌ Не удалось получить список сеансов")
        return False

    sessions.sort(key=lambda s: extract_date_from_title(s['title']))

    existing_data = {}
    if os.path.exists(TICKETS_FILE):
        try:
            with open(TICKETS_FILE, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
        except:
            pass

    updated_count = 0
    total = len(sessions)

    # ОДИН драйвер для всех сеансов
    driver = get_driver()

    try:
        for i, session in enumerate(sessions, 1):
            session_id = str(session['id'])
            print(f"\n[{i}/{total}] Сеанс #{session_id}: {session['title'][:40]}...")

            # 1. Получаем название спектакля
            event_name = get_event_name(driver, session['url'])
            if event_name:
                print(f"   📝 Название: {event_name}")

            # 2. Получаем места
            result = get_available_places(driver, session['url'])

            if result:
                existing_data[session_id] = {
                    'title': session['title'],
                    'event_name': event_name or session['title'],  # ← НОВОЕ ПОЛЕ
                    'url': session['url'],
                    'available': result['available'],
                    'zones': result['zones'],
                    'last_updated': result['last_updated']
                }
                updated_count += 1
                print(f"   ✅ {result['available']} мест")
            else:
                print(f"   ⚠️ Данные не получены")
    finally:
        driver.quit()

    with open(TICKETS_FILE, 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print(f"✅ ОБНОВЛЕНИЕ ЗАВЕРШЕНО")
    print(f"   Всего сеансов: {total}")
    print(f"   Обновлено: {updated_count}")
    print(f"   Данные сохранены в: {TICKETS_FILE}")
    print("=" * 60)
    return True

if __name__ == "__main__":
    update_all_sessions()
