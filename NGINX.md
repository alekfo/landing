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
  -p 127.0.0.1:5000:5000 \
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

## Виртуальные хосты — два сайта на одном порту

Два `server` блока могут слушать один и тот же порт 80. nginx различает их по заголовку `Host`, который браузер передаёт в каждом запросе:

```
http://176.108.247.153  → Host: 176.108.247.153 → попадает в learning_book.conf
http://shlenskov.pro    → Host: shlenskov.pro   → попадает в landing.conf
```

Это называется **виртуальные хосты** — один nginx, много сайтов на одном порту. Запрос к `176.108.247.153` никогда не попадёт в блок `shlenskov.pro` и наоборот — `server_name` работает как фильтр.

---

## Структура конфигов

```
/etc/nginx/
├── nginx.conf                        ← главный файл
├── sites-available/                  ← склад всех конфигов (nginx не читает напрямую)
│   ├── default                       ← дефолтная страница nginx (симлинк удалили)
│   ├── learning_book.conf            ← конфиг для learning_book
│   └── landing.conf                  ← конфиг лендинга
└── sites-enabled/                    ← активные конфиги (nginx читает только отсюда)
    ├── learning_book.conf -> ../sites-available/learning_book.conf
    └── landing.conf       -> ../sites-available/landing.conf
```

В `nginx.conf` есть строка:
```nginx
include /etc/nginx/sites-enabled/*;
```

Именно она говорит nginx: "читай всё из `sites-enabled`". Файл физически лежит в `sites-available`, а `sites-enabled` содержит только символическую ссылку (ярлык) на него.

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

## Как читается конфиг — на примере learning_book (proxy)

```nginx
server {
    listen 80;
    server_name 176.108.247.153;

    location / {
        proxy_pass http://127.0.0.1:5000;        # перенаправить в контейнер
        proxy_set_header Host $host;             # передать оригинальный Host
        proxy_set_header X-Real-IP $remote_addr; # передать реальный IP клиента
    }
}
```

Когда браузер запрашивает `http://176.108.247.153/`:
1. nginx видит: порт 80, `Host: 176.108.247.153` — это мой блок
2. `location /` — подходит любой путь
3. `proxy_pass` — перенаправляет запрос в контейнер на `127.0.0.1:5000`
4. контейнер отвечает → nginx возвращает ответ браузеру

---

## Как читается конфиг — на примере лендинга (статика + proxy)

После получения SSL certbot дописал конфиг, итоговый `landing.conf` на сервере выглядит так:

```nginx
server {
    server_name shlenskov.pro www.shlenskov.pro;

    root /var/www/landing;   # корневая папка с файлами
    index index.html;

    location / {
        try_files $uri $uri/ =404;
        # $uri — путь из запроса, например /style.css
        # ищет файл /var/www/landing/style.css и отдаёт его
        # если не найден — возвращает 404
    }

    location /send {
        proxy_pass http://127.0.0.1:8000/send;  # форма → FastAPI
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # ↓ эти строки certbot добавил сам
    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/shlenskov.pro/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/shlenskov.pro/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
}

server {
    listen 80;
    server_name shlenskov.pro www.shlenskov.pro;
    # ↓ этот блок certbot тоже добавил сам — редирект HTTP → HTTPS
    return 301 https://$host$request_uri;
}
```

Когда браузер запрашивает `https://shlenskov.pro/style.css`:
1. nginx видит: порт 443, `Host: shlenskov.pro` — мой блок
2. `root` + `$uri` → ищет файл `/var/www/landing/style.css`
3. файл есть → отдаёт его напрямую с диска

Когда браузер заходит по `http://shlenskov.pro` (без S):
1. nginx видит: порт 80, `Host: shlenskov.pro` — второй блок
2. `return 301` → редирект на `https://shlenskov.pro`

---

## SSL и certbot — два способа

### Способ 1: `--nginx` (использовали для лендинга)

```bash
sudo certbot --nginx -d shlenskov.pro -d www.shlenskov.pro
```

Certbot сканирует `sites-enabled`, находит блок с нужным `server_name` и **сам дописывает** в него SSL-строки. Конфигурировать вручную не нужно. Требует чтобы nginx был запущен.

### Способ 2: `--standalone` (использовали для fieldlog.ru)

```bash
sudo certbot certonly --standalone -d fieldlog.ru -d www.fieldlog.ru
```

Certbot временно поднимает **свой веб-сервер** на порту 80 для проверки домена. Поэтому перед запуском нужно **остановить nginx** (или контейнер который занимает порт 80) — иначе порт занят и certbot не встанет. После получения сертификата пути прописываются в конфиг вручную.

Оба способа дают одинаковый результат — сертификат в `/etc/letsencrypt/live/домен/`. Разница только в процессе получения.

Сертификат действует 90 дней. certbot автоматически устанавливает задачу на обновление — вручную делать ничего не нужно.

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

## Docker DNS — частая проблема

При первой сборке образа (`docker-compose up --build`) Docker скачивает базовый образ с Docker Hub. Если Docker не может резолвить `registry-1.docker.io` — сборка падает с ошибкой:

```
dial tcp: lookup registry-1.docker.io on 127.0.0.53:53: i/o timeout
```

При этом сервер сам GitHub видит (`ping github.com` работает) — проблема именно в DNS внутри Docker.

Решение — прописать публичный DNS для Docker:

```bash
sudo nano /etc/docker/daemon.json
```
```json
{
  "dns": ["8.8.8.8", "8.8.4.4"]
}
```
```bash
sudo systemctl restart docker
```

---

## Итоговая схема сервера

```
Интернет
    │
    ├── :80
    │     └── nginx
    │           ├── Host: 176.108.247.153 → proxy → 127.0.0.1:5000 (Docker: learning_book)
    │           └── Host: shlenskov.pro   → redirect 301 → https://shlenskov.pro
    │
    └── :443 (SSL)
          └── nginx
                ├── Host: shlenskov.pro  /        → /var/www/landing/ (статика с диска)
                └── Host: shlenskov.pro  /send     → 127.0.0.1:8000   (Docker: FastAPI)
```

Файлы лендинга nginx читает **напрямую с диска** в реальном времени — после `git pull` на сервере статика обновляется без перезапуска nginx.
