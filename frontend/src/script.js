const loginTab = document.getElementById("login-tab");
const registerTab = document.getElementById("register-tab");
const loginForm = document.getElementById("login-form");
const registerForm = document.getElementById("register-form");
const message = document.getElementById("response-message");

// Switch between tabs
loginTab.addEventListener("click", () => {
  loginTab.classList.add("active");
  registerTab.classList.remove("active");
  loginForm.classList.add("active");
  registerForm.classList.remove("active");
  message.textContent = "";
});

registerTab.addEventListener("click", () => {
  registerTab.classList.add("active");
  loginTab.classList.remove("active");
  registerForm.classList.add("active");
  loginForm.classList.remove("active");
  message.textContent = "";
});

const url = window.location.hostname === "localhost"
  ? "http://127.0.0.1:8000"
  : "https://slicerconnect.from-delhi.net";


// Handle Login
loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = document.getElementById("login-email").value;
  const password = document.getElementById("login-password").value;

  try {
    const res = await fetch(`${url}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });

    const data = await res.json();
      if (res.ok) {
      if (data.is_verified === false) {
        message.innerHTML = `
          ⚠️ Your email is not verified.<br>
          <button id="resend-btn">Resend verification link</button>
        `;
        document.getElementById("resend-btn").onclick = resendVerification;
      } else {
        alert(`✅ Welcome back, ${data.user || "User"}!`);
        message.textContent = "";
      }
    } else {
      if (data.detail?.includes("Invalid")) {
        alert("❌ Invalid email or password!");
      } else {
        alert(`⚠️ ${data.detail || "Login failed!"}`);
      }
    }
  } catch (error) {
    alert("⚠️ Error connecting to server.");
  }
});

registerForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = document.getElementById("register-username").value;
  const email = document.getElementById("register-email").value;
  const password = document.getElementById("register-password").value;

  try {
    const res = await fetch(`${url}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, email, password }),
    });

    const data = await res.json().catch(() => ({}));

    if (res.ok) {
      alert("📩 Registered! Please verify your email before logging in.");

      registerForm.reset();
      loginTab.click();
    } else if (Array.isArray(data.detail)) {
      const errors = data.detail.map(err => `⚠️ ${err.loc[1]}: ${err.msg}`).join("\n");
      alert(errors);
    } else if (typeof data.detail === "string") {
      if (data.detail.includes("username")) {
        alert("❌ Username already exists!");
      } else if (data.detail.includes("email")) {
        alert("❌ Email already registered!");
      } else {
        alert(`⚠️ ${data.detail}`);
      }
    } else {
      alert("⚠️ Unknown error occurred.");
    }
  } catch (error) {
    alert("⚠️ Could not connect to backend. Make sure FastAPI is running!");
  }
});

async function resendVerification() {
  const email = document.getElementById("login-email").value;

  if (!email) {
    alert("Enter email first");
    return;
  }

  try {
    const res = await fetch(`${url}/auth/resend-verification`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });

    const data = await res.json();

    if (res.ok) {
      alert("✅ Verification email resent!");
    } else {
      alert(data.detail || "Failed to resend email");
    }
  } catch {
    alert("Server error");
  }
}

