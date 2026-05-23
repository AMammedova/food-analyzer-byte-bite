# Speaking Guide — Byte Bite | AI Food Analyzer
# Oral Defense — ~10 minutes + Q&A

---

## Ümumi zaman bölgüsü

| Slide | Vaxt | Kim danışır |
|-------|------|-------------|
| 1. Title | 0:00 – 0:30 | Aysel |
| 2. Problem | 0:30 – 1:30 | Aysel |
| 3. Architecture | 1:30 – 3:00 | Rəhimə |
| 4. Design Decisions | 3:00 – 4:30 | Aysel |
| 5. Concurrency | 4:30 – 6:00 | Gülnur |
| 6. Robustness | 6:00 – 7:00 | Gülnur |
| 7. Live Demo | 7:00 – 8:00 | Şəmistan |
| 8. Testing | 8:00 – 8:45 | Şəmistan |
| 9. Limitations | 8:45 – 9:30 | Rəhimə |
| 10. Team | 9:30 – 10:00 | Aysel |
| 11. Q&A | 10:00+ | Hamı |

---

## 🎤 AYSEL MAMEDOVA — Slides 1, 2, 4, 10

### Slide 1 — Title (0:30)
> "Salam, biz Byte Bite komandası olaraq AI-ENG-110 kursunun final layihəsini təqdim edirik.
> Mövzumuz Topic 2 — AI Food Analyzer.
> Qısa olaraq: istifadəçi bir yeməyin şəklini yükləyir, sistem Gemini AI vasitəsilə ingredientləri
> müəyyən edir, USDA bazasından qidalanma məlumatlarını alır və kaloriya + makro dəyərləri qaytarır."

---

### Slide 2 — Problem (1:00)
> "Problem çox sadədir: insan yediyi yeməyin kaloriya dəyərini bilmək istəyir, amma hər ingredienti
> əl ilə axtarmaq vaxt aparan bir işdir.
>
> Biz bunu avtomatlaşdırdıq. İstifadəçi üç yoldan biri ilə sistemə daxil ola bilər:
> birinci — veb brauzer üzərindən şəkil yükləmək,
> ikinci — REST API vasitəsilə curl ilə sorğu göndərmək,
> üçüncü — CLI ilə komanda xəttindən işlətmək.
>
> Giriş: JPEG və ya PNG şəkil, maksimum 5 MB.
> Çıxış: hər ingredient üçün qram, kaloriya, zülal, karbohidrat, yağ — və PostgreSQL-ə saxlanan tarixçə."

---

### Slide 4 — Design Decisions (1:30)
> "Üç əsas dizayn qərarını müdafiə edə bilərik.
>
> Birincisi — **kompozisiya vs inheritance**.
> `FoodAnalyzer` sinifi `AIService` və `NutritionPipeline`-ı irs almır, əksinə, konstruktora argument kimi alır.
> Niyə? Çünki analyzer bu servisləri genişləndirir yox, istifadə edir.
> Bu bizə test zamanı real API-yə qoşulmadan fake provayderlərlə test etməyə imkan verdi.
>
> İkincisi — **asyncio vs threading**.
> USDA sorğuları I/O-bound-dur, CPU-bound deyil. asyncio burada ən düzgün seçimdir.
> Threading üstgəldi olmadan artıq komplekslik gətirərdi.
>
> Üçüncüsü — **pydantic-settings**.
> Bütün mühit dəyişkənlərini bir `Settings` sinfindən oxuyuruq, tip xətalari server başlamazdan əvvəl aşkarlanır."

---

### Slide 10 — Team (0:30)
> "Komandamızın 4 üzvünün hər biri layihənin müəyyən hissəsinə sahib idi.
> Mən konfiqurasiyon, model, validasiya, CLI, Docker və veb UI-yə cavabdeh idim.
> Hər üzv öz modulunu sıfırdan yaratdı — oral müdafiədə hər hansı faylı açın, müdafiə edəcəyik."

---

## 🎤 GÜLNUR MƏMMƏDOVA — Slides 5, 6

### Slide 5 — Concurrency (1:30)
> "Mənim əsas işim layihənin ən vacib SE komponentlərindən biri idi — paralel pipeline.
>
> Problem belədir: bir yeməkdə 5–7 ingredient ola bilər. Hər ingredient üçün ayrıca USDA API sorğusu
> göndərsəydik, ardıcıl olaraq 5 saniyə gözləyərdik.
>
> Həlli belə qurdum: `NutritionPipeline.fetch_all()` metodu bütün USDA sorğularını eyni anda
> `asyncio.gather` ilə işə salır. `Semaphore(10)` isə USDA API-nin rate limitini aşmamaq üçün
> eyni anda maksimum 10 sorğuya icazə verir.
>
> Nəticə: 5 ingredient üçün ardıcıl 2.50 saniyə idi, paralel versiya 0.53 saniyəyə düşdü — 4.8x sürətlənmə.
> Yeni darboğaz artıq USDA yox, Gemini VLM sorğusudur — çünki o ardıcıl işləyir, bir şəkil, bir cavab."

---

### Slide 6 — Robustness (1:00)
> "Mən həmçinin bütün AI çağırışları üçün retry və caching mexanizmini qurdum.
>
> Real bir xəta ilə üz-üzə gəldik: Gemini SDK versiyası 0.3.0-da `Files.upload()` metodu dəstəklənmirdi.
> tenacity avtomatik 4 dəfə yenidən cəhd etdi — hər dəfə xəta verdi.
> Loqlarda aydın görünürdü: `attempt=1,2,3,4`, `exc_type=TypeError`.
> Son olaraq HTTP 500 — amma istifadəçiyə stack trace deyil, aydın JSON mesajı göstərildi.
>
> Həll sadə oldu: `types.Part.from_bytes()` — şəkli inline byte kimi göndəririk, files API lazım deyil.
>
> Caching tərəfinə gəlincə: eyni ingredient adı üçün USDA 24 saat cache-lənir.
> 16 nümunə şəkli üzərindən test zamanı cache hit rate 60%-dən yuxarı oldu."

---

## 🎤 ŞƏMİSTAN HÜSEYNOv — Slides 7, 8

### Slide 7 — Demo (1:00)
> "Mən layihənin HTTP API hissəsinə sahib idim — FastAPI ilə `POST /analyze`, `GET /history`, `GET /health` endpointlərini qurdum.
>
> İndi canlı demo göstərəcəm. [Brauzeri aç → localhost:8000]
>
> İstifadəçi şəkli drag-and-drop edir — burada `rice_chicken.png` götürək.
> [Şəkli yüklə]
> Göründüyü kimi: sistem ingredientləri, hər birinin qram, kaloriya, makro dəyərlərini qaytardı.
> Tarixçə bölməsindəki bu analiz PostgreSQL verilənlər bazasına yazıldı.
>
> Eyni nəticəni curl ilə də ala bilərsiniz — API tamamilə RESTful-dur."

---

### Slide 8 — Testing (0:45)
> "API üçün testlər yazdım — ümumilikdə 158 test, hamısı offline işləyir, real API sorğusu yoxdur.
>
> Üç vacib test qeyd etmək istəyirəm:
> Birincisi — happy-path: real PNG şəkli `POST /analyze`-ə göndəririk, HTTP 200 alırıq,
> `meal_recognized=True`, kaloriya sıfırdan böyükdür.
>
> İkincisi — concurrency xətası: 5 ingredientdən biri USDA-dan xəta alır. Test yoxlayır ki,
> qalan 4-ün nəticəsi qaytarılsın, sistem çöksün yox.
>
> Üçüncüsü — validasiya: `.jpg` uzantılı amma PDF magic byte-lı fayl göndəririk.
> Sistem API çağırmazdan əvvəl rədd edir — bu real bir bug-ı aşkar etdi."

---

## 🎤 RƏHİMƏ KƏRİMOVA — Slides 3, 9

### Slide 3 — Architecture (1:30)
> "Mənim əsas işim layihənin iki kritik hissəsi idi: verilənlər bazası sloju və `FoodAnalyzer` orkestrasiyası.
>
> Arxitektura diaqramına baxsaq: istifadəçi sorğusu FastAPI-ya gəlir, oradan `FoodAnalyzer`-ə keçir.
> Analyzer 4 addımı ardıcıl koordinasiya edir:
> Birinci — şəkil validasiyası, ikinci — Gemini VLM sorğusu (AIService vasitəsilə, retry ilə),
> üçüncü — paralel USDA sorğuları (NutritionPipeline vasitəsilə), dördüncü — nəticəni DB-yə yazmaq.
>
> Mən `asyncpg` ilə PostgreSQL bağlantı pool-unu qurdum. Sxema çox sadədir:
> bir `analyses` cədvəli, ID, şəkil yolu, tam nəticə JSON kimi, yaradılma tarixi.
> Startup zamanı sxema avtomatik yaradılır.
>
> Loqlaşdırma tərəfindən isə `StructuredFormatter` yazdım — human-readable format,
> key=value əlavə məlumatlarla, JSON rejimdə də işləyir."

---

### Slide 9 — Limitations (0:45)
> "Hər layihənin məhdudiyyətləri olur — bizimkini dürüstcə qeyd edək.
>
> Ən böyük problem: nutrition cache yalnız RAM-dadır. Server yenidən başlayanda sıfırlanır.
> Həlli Redis olardı — lakin kurs çərçivəsindən çox idi.
>
> İkincisi: şəkillər lokal fayl sistemindədir. Əgər birdən çox server instance olsaydı,
> şəkillərə hamı giriş edə bilməzdi. S3 kimi object store bu problemi həll edər.
>
> Üçüncüsü: USDA axtarışı mətndən asılıdır. Gemini tanınmayan bir yemək adı qaytararsa,
> USDA 0 qaytarır, sistem bunu susdurur. Fuzzy match əlavə etmək lazım idi.
>
> Növbəti həftə vaxtımız olsaydı: Redis cache, GitHub Actions CI, multi-provider failover qurardıq."

---

## Gözlənilən Q&A sualları və cavablar

**S: asyncio.gather exception-ı necə idarə edir?**
> G: `return_exceptions=True` istifadə edirik — bir task xəta versə, qalanlar ləğv edilmir.
> Nəticəni filterləyirik: uğurlu olanlar qaytarılır, xətalı olanlar loglanır.
> Bu testi yazdıq: `test_one_task_raises_others_complete`.

**S: Niyə PostgreSQL, SQLite yox?**
> R: Kurs tələbi PostgreSQL göstərirdi. Həm də asyncpg tam async dəstəyi olan bir client — SQLite üçün belə bir alternativ yox idi ki layihəmizin tam async arxitekturasına uyğun olsun.

**S: pydantic-settings os.getenv-dən nə fərqi var?**
> A: pydantic-settings `.env`-i oxuyur, tip yoxlaması aparır, startup zamanı xəta verir.
> Amma os.environ-ə yazmır — bunu kəşf etdik. Buna görə `api.py`-da `load_dotenv()` çağırışı əlavə etdik ki AI modulu provayderləri də mühit dəyişkənlərini görə bilsin.

**S: Config.py saxlanılan API key var?**
> A: Yox. `.env` `.gitignore`-dadır, heç bir faılda real key commit edilməyib. `.env.example` isə placeholder-larla repodadır.

**S: 79% coverage kifayətdirmi?**
> Ş: Kurs tələbi 60%-dir, biz 79% çatdırdıq. Əsas boşluq `cli.py`-dır (0% — subprocess test yoxdur), lakin CLI-yi əl ilə test etdik, düzgün işləyir.

**S: Gemini `ai/` package-nı dəyişdirdinizmi?**
> A: `google.py` faylında bir üsul dəyişdirdik — `Files.upload` yerini `Part.from_bytes` aldı.
> Bu publik interfeysin dəyişdirilməsi deyil, daxili implementasiyanın SDK-ya uyğunlaşdırılmasıdır.
> `ai/vlm.py`-ın publik `identify_ingredients()` funksiyası tam dəyişməz qaldı.

---

## Müdafiə üçün yadda saxla

- Hər kəs **öz modulunun** hər sətirini izah edə bilməlidir
- "AI yazdı" — qəbul edilmir
- Sual gəlirsə, hamı sakitcə dinləsin, cavabı kim bilirsa o danışsın
- Demo işləməsə — curl backup-ı var, `artefacts/api_sample_output.json` da var
