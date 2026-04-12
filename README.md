"# SlicerConnectBackend" 
---

## Tech Stack
| Layer                  | Technology Used                     |
| ---------------------- | ----------------------------------- |
| Backend                | FastAPI (Python)                    |
| Frontend               | HTML, CSS, JavaScript               |
| Database               | SQLite (via SQLAlchemy ORM)         |
| Security               | Passlib (bcrypt), hashlib, jose JWT |
| Environment Management | python-dotenv                       |
| Web Server             | Uvicorn                             |

---


## Deployment Instructions:

OfCourse:
```bash
git clone https://github.com/pka420/SlicerConnectbackend.git
```

1. Have your domain ready and certs ready, if you are relying on cloudflare like me, you can use certbot with api token:
``` bash
cd certbot
sudo docker build -t certbot .
sudo docker run --rm -v /etc/letsencrypt:/etc/letsencrypt  --env site_url="https://your_domain" --env user_email="your_email" certbot
cd ../
```

2. Setup .env file with following vars:
```bash
# .env
POSTGRES_USER=slicer
POSTGRES_PASSWORD="good_password"
POSTGRES_DB=slicer
POSTGRES_PORT=5432
FRONTEND_URL=https://your-domain
DATABASE_URL=postgresql://slicer:good_password@slicer_db:5432/slicer
SECRET_KEY="whatever_you_want"
MAIL_SERVER=mailserver
MAIL_PORT=25
MAIL_USER=noreply@your-domain
MAIL_PASS=StrongPassword123
MAIL_FROM=verify@your-domain
ENABLE_SPAMASSASSIN=0
ENABLE_CLAMAV=0
ENABLE_FAIL2BAN=1
ENABLE_POSTGREY=0
ENABLE_SASLAUTHD=0
ONE_DIR=1
PERMIT_DOCKER=network
SMTP_ONLY=1
SMTP_PASSWORD=superstrongpassword
SSL_TYPE=none
DOMAIN=your-domain
HOSTNAME=mail
```

Also copy this to backend folder.

2. Use docker to create the backend
```bash
sudo docker compose up -d 
```

3. Finish setting up Database:
```bash
sudo docker exec -it slicer_backend /bin/bash
mkdir alembic/versions
alembic revision --autogenerate -m "init"
alembic upgrade head
```

This is in active development, once we lock down a version, the end user won't
have to generate db revision

3. Mailserver
```bash
sudo docker exec -ti mailserver setup config dkim
sudo docker cp mailserver:/tmp/docker-mailserver/opendkim/keys/ ./
#Then copy your keys/your-domain/mail.txt (public key) to dns records
sudo docker restart mailserver
```
And offcourse then you have to copy-paste these records into your dns records
for email to work....bla bla bla.

## Installation & Setup for development

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/pka420/SlicerConnectbackend.git
cd backend
```

### 2️⃣ Create a Virtual Environment

```bash
python3.13 -m venv venv
source venv/bin/activate     # on macOS/Linux
venv\Scripts\activate        # on Windows
pip install --upgrade pip
```

### 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

### 4️⃣ Run the Server

```bash
uvicorn main:app --reload
```

The backend will start at:
**[http://127.0.0.1:8000](http://127.0.0.1:8000)**

## Coming from Django World
makemigrations | alembic revision --autogenerate -m "message"
migrate | alembic upgrade head
migrate app <previd> | alembic downgrade -1
showmigrations | alembic history --indicate-current
