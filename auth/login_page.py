"""
auth/login_page.py
Dark-themed HTML login page for Oasia.
"""
from __future__ import annotations

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Oasia — Sign In</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600&family=DM+Mono&display=swap" rel="stylesheet"/>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      min-height: 100vh;
      background: #0F172A;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: 'DM Sans', sans-serif;
    }
    .card {
      width: 380px;
      background: #1E293B;
      border: 1px solid #334155;
      border-radius: 16px;
      padding: 40px 36px 36px;
      box-shadow: 0 24px 48px rgba(0,0,0,0.4);
    }
    .brand {
      font-family: 'DM Serif Display', serif;
      font-size: 28px;
      color: #F1F5F9;
      letter-spacing: -0.5px;
      margin-bottom: 4px;
    }
    .subtitle {
      font-size: 13px;
      color: #64748B;
      margin-bottom: 32px;
    }
    .field { margin-bottom: 16px; }
    label {
      display: block;
      font-size: 11px;
      font-weight: 600;
      color: #94A3B8;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-bottom: 6px;
    }
    input[type=text], input[type=password] {
      width: 100%;
      padding: 10px 12px;
      background: #0F172A;
      border: 1.5px solid #334155;
      border-radius: 8px;
      color: #F1F5F9;
      font-family: 'DM Mono', monospace;
      font-size: 13px;
      outline: none;
      transition: border-color 0.2s;
    }
    input[type=text]:focus, input[type=password]:focus {
      border-color: #3B6FD4;
      box-shadow: 0 0 0 3px rgba(59,111,212,0.15);
    }
    .error {
      background: rgba(229,72,77,0.1);
      border: 1px solid rgba(229,72,77,0.3);
      border-radius: 8px;
      color: #F87171;
      font-size: 12px;
      padding: 10px 12px;
      margin-bottom: 16px;
    }
    .btn {
      width: 100%;
      padding: 11px;
      background: #3B6FD4;
      border: none;
      border-radius: 8px;
      color: #fff;
      font-family: 'DM Sans', sans-serif;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      margin-top: 8px;
      transition: background 0.2s;
    }
    .btn:hover { background: #2F5BB8; }
    .footer {
      margin-top: 24px;
      font-size: 11px;
      color: #475569;
      text-align: center;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="brand">Oasia</div>
    <div class="subtitle">Agency MBS &nbsp;·&nbsp; Sign in with your company account</div>
    {{error_block}}
    <form method="POST" action="/login">
      <div class="field">
        <label>Username</label>
        <input type="text" name="username" autocomplete="username" autofocus required placeholder="domain\\username or user@company.com"/>
      </div>
      <div class="field">
        <label>Password</label>
        <input type="password" name="password" autocomplete="current-password" required placeholder="••••••••"/>
      </div>
      <button class="btn" type="submit">Sign In</button>
    </form>
    <div class="footer">Oasia &nbsp;·&nbsp; Fixed Income Portfolio</div>
  </div>
</body>
</html>"""


def render_login_page(error: str = "") -> str:
    if error:
        error_block = f'<div class="error">{error}</div>'
    else:
        error_block = ""
    return LOGIN_HTML.replace("{{error_block}}", error_block)
