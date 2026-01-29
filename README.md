"# Slicerbackend" 

#  Authentication System (FastAPI + HTML/JS Frontend)

A simple yet powerful **user authentication system** built with **FastAPI (Python)** for the backend and **HTML, CSS, and JavaScript** for the frontend.
This project demonstrates secure **user registration and login** functionality with hashed passwords, form validation, and a clean UI — ideal for software engineering and web development learning purposes.

---

## Features

✅ **User Registration** — Register with username, email, and password.
✅ **User Login** — Secure login using JWT authentication.
✅ **Password Hashing** — SHA256 + bcrypt for strong password protection.
✅ **Duplicate Check** — Prevents duplicate email or username registration.
✅ **Frontend Integration** — Connects seamlessly to FastAPI backend via Fetch API.
✅ **SQLite Database** — Stores user credentials safely.
✅ **Interactive Alerts** — Real-time feedback for success/failure actions.
✅ **Modular Codebase** — Clean separation between backend and frontend files.

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

## 📂 Project Structure

```
📁 backend/
│
├── main.py          # FastAPI main entry point
├── auth.py          # Authentication routes (register/login)
├── models.py        # SQLAlchemy user model
├── database.py      # DB connection setup
├── .env             # Environment variables (SECRET_KEY, etc.)
│
📁 frontend/
│
├── index.html       # Login/Register page
├── style.css        # Modern responsive UI design
├── script.js        # Frontend logic & backend API connection
```

---

## ⚙️ Installation & Setup

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/i-Pradeepkhatri/SlicerConnectbackend.git
cd backend
```

### 2️⃣ Create a Virtual Environment

```bash
python3.11 -m venv venv
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

✅ The backend will start at:
**[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 🖥️ Frontend Setup

1. Open the `index.html` file in your browser.
2. Use the **Register** tab to create an account.
3. Use the **Login** tab to log in with your registered credentials.
4. You’ll receive success/error messages in real time.

---

## API Endpoints

| Endpoint         | Method | Description                          |
| ---------------- | ------ | ------------------------------------ |
| `/auth/register` | POST   | Register a new user                  |
| `/auth/login`    | POST   | Authenticate user & return token     |
| `/docs`          | GET    | Swagger UI for testing API endpoints |

---

## Security

* Passwords are hashed using **SHA256 + bcrypt** (avoids 72-byte bcrypt limit).
* JWT (JSON Web Token) is used for secure session management.
* No plain-text password storage.
* Proper input validation and error handling.

---

## Database

* Uses **SQLite** by default (via SQLAlchemy).
* File: `users.db` (auto-created).
* Stores: `id`, `username`, `email`, `hashed_password`.

---

## Testing API with Swagger

FastAPI provides an inbuilt Swagger UI at:
👉 **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)**

You can test registration and login APIs directly from there.

---

## 📸 Screenshots

| Login Page                                                           
| ---------------------------------------------------------------------------------------------------------------------------------------------------------|
| ![Login Screenshot](<img width="1918" height="965" alt="image" src="https://github.com/user-attachments/assets/bef132b1-ddb7-46b1-ab57-26e27b6b9b6c" />)
 
 
| Register Page                                                                 
| ----------------------------------------------------------------------------------------------------------------------------------------------------------|
| ![Register Screenshot](<img width="1919" height="973" alt="image" src="https://github.com/user-attachments/assets/cc7f17cf-6234-44ab-91f8-91f5ae19df86" />)

---

## Future Enhancements

* ✅ Forgot password functionality
* ✅ JWT-based session handling in frontend
* ✅ Email verification
* ✅ Dark/light theme toggle

---

## 👨‍💻 Author

**Pradeep Kumar**
B.Sc. (Hons) Computer Science, Delhi University
📅 Created: 2025
💼 Project Type: Research paper project backend

---


