# nginx — как это работает

## Что такое nginx

nginx — программа, которая устанавливается на сервер и **слушает порты**. Когда браузер делает запрос, nginx смотрит в свои конфиги и решает что ответить.

После `apt install nginx` он сразу запускается как системный сервис и слушает порт 80.

---

## Порты: 80 и 443

- **80** — обычный HTTP (`http://сайт.ru`)
- **443** — зашифрованный HTTPS (`https://сайт.ru`)

Порт может занимать только **одна** программа одновременно. Именно поэтому у нас был конфликт: контейнер `learning_book` занял порт 80 через `-p 80:5000`, и когда nginx попытался встать на тот же порт — упал с ошибкой:

```
bind() to 0.0.0.0:80 failed (98: Address already in use)
```

---

## Как мы решили конфликт

Раньше:
```
Браузер :80 → Docker контейнер learning_book (монопольно держит порт 80)
```

Проблема: никто другой на порт 80 встать не может.

Решение — убрать контейнер с публичного порта и спрятать его за nginx:

```bash
docker stop learning_book
docker rm learning_book
docker run -d \
  --name learning_book \
  --restart unless-stopped \
  -p 127.0.0.1:5000:5000 \       # ← теперь слушает только локально
  alekfo123/learning_book:v.1.4
```

Теперь:
```
Браузер :80 → nginx (держит порт 80 один)
                ├── 176.108.247.153 → proxy_pass 127.0.0.1:5000 (learning_book)
                └── shlenskov.pro   → /var/www/landing/index.html (лендинг)
```

nginx — единственный кто торчит наружу. Контейнер слушает только `127.0.0.1:5000` — снаружи к нему напрямую не достучаться, только через nginx.

---

## Структура конфигов

```
/etc/nginx/
├── nginx.conf                        ← главный файл
├── sites-available/                  ← склад всех конфигов (nginx не читает)
│   ├── default                       ← дефолтная страница nginx (удалили симлинк)
│   ├── learning_book.conf            ← конфиг learning_book
│   └── landing.conf                  ← конфиг лендинга (добавим позже)
└── sites-enabled/                    ← активные конфиги (nginx читает только отсюда)
    └── learning_book.conf -> ../sites-available/learning_book.conf  ← симлинк
```

В `nginx.conf` есть строка:
```nginx
include /etc/nginx/sites-enabled/*;
```

Именно она говорит nginx: "читай всё из `sites-enabled`". Поэтому схема с симлинками работает — файл физически лежит в `sites-available`, а `sites-enabled` содержит только ярлык на него.

**sites-available** — склад. Там хранятся все конфиги, включая неактивные.  
**sites-enabled** — витрина. Только то, что nginx реально читает.

Добавить конфиг в работу:
```bash
sudo ln -s /etc/nginx/sites-available/landing.conf /etc/nginx/sites-enabled/
```

Убрать конфиг из работы (файл не трогаем):
```bash
sudo rm /etc/nginx/sites-enabled/landing.conf
```

---

## Как читается конфиг — на примере learning_book

```nginx
server {
    listen 80;                        # слушать порт 80
    server_name 176.108.247.153;      # реагировать на этот адрес

    location / {                      # для всех запросов (/, /page, /img/a.png)
        proxy_pass http://127.0.0.1:5000;        # перенаправить в контейнер
        proxy_set_header Host $host;             # передать оригинальный Host
        proxy_set_header X-Real-IP $remote_addr; # передать реальный IP клиента
    }
}
```

Когда браузер запрашивает `http://176.108.247.153/`:
1. nginx видит: порт 80, адрес `176.108.247.153` — это мой `server` блок
2. смотрит `location /` — подходит любой путь
3. `proxy_pass` — перенаправляет запрос в контейнер на `127.0.0.1:5000`
4. контейнер отвечает → nginx возвращает ответ браузеру

---

## Как читается конфиг — на примере лендинга (статика)

```nginx
server {
    listen 443 ssl;
    server_name shlenskov.pro;

    root /var/www/landing;       # корневая папка с файлами
    index index.html;            # файл по умолчанию

    location / {
        try_files $uri $uri/ =404;
        # $uri — путь из запроса, например /style.css
        # ищет файл /var/www/landing/style.css и отдаёт его
        # если не найден — возвращает 404
    }

    location /send {
        proxy_pass http://127.0.0.1:8000/send;  # форма → FastAPI
    }
}
```

Когда браузер запрашивает `https://shlenskov.pro/style.css`:
1. nginx видит: порт 443, домен `shlenskov.pro` — мой блок
2. `root` + `$uri` → ищет файл `/var/www/landing/style.css`
3. файл есть → отдаёт его напрямую с диска

Когда форма отправляет POST на `https://shlenskov.pro/send`:
1. nginx видит `location /send` — это proxy
2. перенаправляет в FastAPI на `127.0.0.1:8000`

---

## SSL и certbot

HTTPS требует сертификат — файл, который подтверждает что домен принадлежит тебе.

`certbot` — утилита, которая получает бесплатный сертификат от Let's Encrypt и сама прописывает его в nginx конфиг:

```bash
sudo certbot --nginx -d shlenskov.pro -d www.shlenskov.pro
```

После этого certbot:
1. Получает сертификат (кладёт в `/etc/letsencrypt/live/shlenskov.pro/`)
2. Дописывает в конфиг строки `ssl_certificate ...`
3. Добавляет редирект HTTP → HTTPS
4. Перезагружает nginx

Сертификат действует 90 дней. certbot автоматически устанавливает задачу на обновление — делать вручную ничего не нужно.

---

## Управление nginx

```bash
sudo systemctl start nginx      # запустить
sudo systemctl stop nginx       # остановить
sudo systemctl restart nginx    # полный перезапуск (секундный даунтайм)
sudo systemctl reload nginx     # перечитать конфиги без даунтайма ← используй это
sudo systemctl status nginx     # посмотреть статус и последние ошибки

sudo nginx -t                   # проверить синтаксис конфигов
```

**Правило:** перед каждым `reload` делай `nginx -t`. Если синтаксис сломан — nginx откажется перезагружаться и текущий сайт не упадёт.

nginx добавлен в автозапуск (`enabled`) — после перезагрузки сервера стартует сам.

---

## Итоговая схема сервера

```
Интернет
    │
    ▼  :80 / :443
  nginx
    │
    ├── server_name 176.108.247.153  :80
    │       └── proxy → 127.0.0.1:5000  (Docker: learning_book)
    │
    └── server_name shlenskov.pro   :443 (SSL)
            ├── /       → /var/www/landing/  (статика с диска)
            └── /send   → 127.0.0.1:8000     (Docker: FastAPI бэкенд)
```
