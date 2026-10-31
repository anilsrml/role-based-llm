import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from faker import Faker
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from rolchat.models import (
    ADMIN_DATABASE_URL,
    TABLE_LEVELS,
    Announcement,
    Employee,
    FinancialSummary,
    Leave,
    Meeting,
    Salary,
    Shift,
)

DOMAIN = "anadolumakina.example"
ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")

# (title, department); the first row is the boss.
STAFF = [
    ("Genel Müdür", "Yönetim"),
    ("Yönetici Asistanı", "Yönetim"),
    ("Muhasebe Uzmanı", "Finans"),
    ("İnsan Kaynakları Uzmanı", "İnsan Kaynakları"),
    ("Üretim Şefi", "Üretim"),
    ("Kalite Kontrol Uzmanı", "Üretim"),
    ("Montaj Operatörü", "Üretim"),
    ("Montaj Operatörü", "Üretim"),
    ("Montaj Operatörü", "Üretim"),
    ("Paketleme Operatörü", "Üretim"),
    ("Paketleme Operatörü", "Üretim"),
    ("Depo Sorumlusu", "Lojistik"),
    ("Depo Görevlisi", "Lojistik"),
    ("Forklift Operatörü", "Lojistik"),
    ("Bakım Teknisyeni", "Teknik"),
]

GROSS_RANGE = {
    "Genel Müdür": (240_000, 260_000),
    "Yönetici Asistanı": (60_000, 70_000),
    "Muhasebe Uzmanı": (65_000, 80_000),
    "İnsan Kaynakları Uzmanı": (60_000, 75_000),
    "Üretim Şefi": (75_000, 90_000),
    "Kalite Kontrol Uzmanı": (50_000, 60_000),
}
DEFAULT_GROSS = (34_000, 45_000)

ANNOUNCEMENTS = [
    ("Yemekhane menüsü güncellendi", "Bu haftadan itibaren öğle yemeğinde vejetaryen seçenek de sunulacaktır."),
    ("İş güvenliği eğitimi", "Tüm üretim personelinin yıllık iş güvenliği eğitimine katılması zorunludur. Eğitim toplantı salonunda yapılacaktır."),
    ("Servis güzergahı değişikliği", "Kadıköy servisi yol çalışması nedeniyle bir süre Bostancı üzerinden gidecektir."),
    ("Bayram tatili", "Bayram süresince fabrika kapalı olacaktır. Vardiya planı bayram sonrası yeniden yayınlanacaktır."),
    ("Yeni kişisel koruyucu ekipmanlar", "Yeni iş ayakkabıları ve eldivenler depodan imza karşılığı teslim alınabilir."),
    ("Kan bağışı kampanyası", "Kızılay kan bağışı aracı Cuma günü fabrika otoparkında olacaktır."),
    ("Otopark düzenlemesi", "Otoparkın arka bölümü boyama çalışması nedeniyle iki gün kapalı kalacaktır."),
    ("Yangın tatbikatı", "Önümüzdeki hafta habersiz bir yangın tatbikatı yapılacaktır. Lütfen tahliye planlarını inceleyiniz."),
    ("Öneri kutusu", "Üretim süreçleriyle ilgili önerilerinizi giriş kapısındaki öneri kutusuna bırakabilirsiniz."),
    ("Kışlık iş kıyafetleri", "Kışlık montlar dağıtılmaya başlanmıştır. Bedeninizi vardiya amirinize bildiriniz."),
]

# name, start, end
SHIFT_TYPES = [
    ("Sabah", time(8, 0), time(16, 0)),
    ("Akşam", time(16, 0), time(0, 0)),
    ("Gece", time(0, 0), time(8, 0)),
]
TEAMS = ["Montaj", "Paketleme", "Depo"]

LEAVE_TYPES = ["Yıllık izin", "Yıllık izin", "Yıllık izin", "Hastalık izni", "Mazeret izni", "Ücretsiz izin"]

MEETINGS = [
    ("Haftalık üretim değerlendirmesi", "Toplantı Salonu"),
    ("Aylık bütçe toplantısı", "Genel Müdür Odası"),
    ("Tedarikçi görüşmesi", "Toplantı Salonu"),
    ("Kalite denetimi hazırlığı", "Üretim Ofisi"),
    ("İşe alım mülakatları", "İK Ofisi"),
    ("Bakım planı toplantısı", "Teknik Ofis"),
]


def seed(session: Session, rng_seed: int = 42) -> None:
    rng = random.Random(rng_seed)
    fake = Faker("tr_TR")
    fake.seed_instance(rng_seed)
    # Dates follow the run day so "today's shifts" etc. stay meaningful; everything else is fixed by the seed.
    today = date.today()

    # TRUNCATE is transactional in Postgres, so clear + insert commit together.
    session.execute(text(f"TRUNCATE {', '.join(TABLE_LEVELS)} RESTART IDENTITY CASCADE"))

    employees = []
    for title, department in STAFF:
        first, last = fake.first_name(), fake.last_name()
        local = f"{first}.{last}".translate(ASCII).lower().replace(" ", "")
        employees.append(Employee(
            full_name=f"{first} {last}",
            title=title,
            department=department,
            phone=fake.numerify("053# ### ## ##"),
            email=f"{local}@{DOMAIN}",
        ))
    session.add_all(employees)
    session.flush()  # assigns ids for the foreign keys below

    session.add_all(
        Announcement(title=t, body=b, published_on=today - timedelta(days=rng.randint(0, 60)))
        for t, b in ANNOUNCEMENTS
    )

    monday = today - timedelta(days=today.weekday())
    for offset in range(14):
        day = monday + timedelta(days=offset)
        week = offset // 7
        for i, team in enumerate(TEAMS):
            name, start, end = SHIFT_TYPES[(i + week) % 3]  # teams rotate shift weekly
            session.add(Shift(day=day, name=name, start_time=start, end_time=end, team=team))

    for _ in range(8):
        start = today + timedelta(days=rng.randint(-30, 60))
        session.add(Leave(
            employee_id=rng.choice(employees[1:]).id,
            start_date=start,
            end_date=start + timedelta(days=rng.randint(0, 9)),
            leave_type=rng.choice(LEAVE_TYPES),
        ))

    for title, location in MEETINGS:
        day = today + timedelta(days=rng.randint(-7, 21))
        session.add(Meeting(
            title=title,
            starts_at=datetime.combine(day, time(rng.choice([9, 10, 11, 14, 15]), rng.choice([0, 30]))),
            location=location,
            attendees=", ".join(e.full_name for e in rng.sample(employees, rng.randint(2, 5))),
        ))

    for e in employees:
        low, high = GROSS_RANGE.get(e.title, DEFAULT_GROSS)
        session.add(Salary(
            employee_id=e.id,
            monthly_gross=Decimal(rng.randrange(low, high, 250)),
            effective_from=date(today.year, 1, 1),
        ))

    # The 12 full months before the current one.
    cash = Decimal(rng.randrange(2_000_000, 3_000_000, 1000))
    year, month = today.year, today.month
    periods = []
    for _ in range(12):
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
        periods.append(date(year, month, 1))
    for period in reversed(periods):
        revenue = Decimal(rng.randrange(4_000_000, 6_000_000, 1000))
        expenses = Decimal(rng.randrange(3_500_000, 5_200_000, 1000))
        profit = revenue - expenses
        cash += profit
        session.add(FinancialSummary(
            period=period, revenue=revenue, expenses=expenses, profit=profit, cash_balance=cash,
        ))

    session.commit()


if __name__ == "__main__":
    engine = create_engine(ADMIN_DATABASE_URL)
    with Session(engine) as session:
        seed(session)
    print("Seeded:", ", ".join(TABLE_LEVELS))
