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

## Installation & Setup

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/i-Pradeepkhatri/SlicerConnectbackend.git
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


## Code Structure:
